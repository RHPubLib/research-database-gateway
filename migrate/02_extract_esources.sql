-- ===========================================================================
-- eResources migration -- STEP 2: extract the eSource catalog from Polaris
-- ===========================================================================
-- Run against the Polaris `Polaris` database (read-only). Produces THREE
-- result sets; save each as CSV (UTF-8) for import_extract.py:
--
--   Query A -> migrate/extract/esources.csv     (one row per database)
--   Query B -> migrate/extract/categories.csv   (parent EntryID -> name)
--   Query C -> migrate/extract/parameters.csv   (one row per Parameter attribute)
--
-- Query A also carries a `launch_parameters` column with all of the entry's
-- Parameter rows joined by CHAR(10) (newline) -- the import script can use
-- either source. Query C is the authoritative source of truth if Query A's
-- aggregation is ever in doubt.
--
-- What this extract assumes (verified against 01_discover_attributes.sql
-- output on 2026-05-23):
--   * The record-type discriminator is 'E-Source Object'. Real databases are
--     'ETarget'; 'ESubject' is a category record (handled in Query B);
--     'Z39.50 Object' / 'AppServer Object' are old federated-search wiring
--     and are ignored.
--   * RHPL's primary OrganizationID is 1 (247 ETargets). Orgs 2 and 3
--     (23 ETargets each) are out of scope for the cutover.
--   * Credentials are NOT in SA_DWI_UserName_Password_Usage (that table is
--     empty). They live as Parameter attribute rows -- key=value strings
--     appended to the launch URL.
--   * There is NO 'EM' attribute. Access is controlled by InHouseAccess /
--     RemoteAccess enum attributes:
--         1 = Open (no auth)
--         2 = Patron-authenticated (library card required)
--         3 = IP-authorized only (in-library; blocked off-site)
-- ===========================================================================

-- --- Query A: one row per eSource database (Org 1 ETargets only) -----------
SELECT
    e.EntryID                                                AS legacy_entry_id,
    e.CommonName                                             AS name,
    MAX(CASE WHEN a.AttributeType = 'URL'                   THEN a.Value END) AS url,
    MAX(CASE WHEN a.AttributeType = 'Description'           THEN a.Value END) AS description,
    MAX(CASE WHEN a.AttributeType = 'Message'               THEN a.Value END) AS message,
    MAX(CASE WHEN a.AttributeType = 'InHouseAccess'         THEN a.Value END) AS in_house_access,
    MAX(CASE WHEN a.AttributeType = 'RemoteAccess'          THEN a.Value END) AS remote_access,
    MAX(CASE WHEN a.AttributeType = 'ESourceTransferTypeID' THEN a.Value END) AS transfer_type,
    do.ParentEntryID                                         AS parent_entry_id,
    do.DisplayOrder                                          AS display_order,
    -- Aggregate every Parameter row for this entry into a newline-delimited
    -- string. Parameter values are URL query-string pieces (key=value); they
    -- cannot contain newlines, so CHAR(10) is a safe in-band separator.
    STUFF(
      (SELECT CHAR(10) + p.Value
       FROM DWIViewEntryAttributes p
       WHERE p.EntryID = e.EntryID
         AND p.AttributeType = 'Parameter'
       FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'),
      1, 1, ''
    )                                                        AS launch_parameters,
    -- Aggregate any PatronCodeID rows (max 10 per entry) as a comma list.
    -- These are the patron-code BLOCK-LIST -- Polaris UI labels them
    -- "patron codes to restrict". A selected code blocks that patron type.
    -- (Investigated 2026-05-23; see migrate/03_discover_patroncode_polarity.sql.)
    STUFF(
      (SELECT ',' + pc.Value
       FROM DWIViewEntryAttributes pc
       WHERE pc.EntryID = e.EntryID
         AND pc.AttributeType = 'PatronCodeID'
       FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'),
      1, 1, ''
    )                                                        AS blocked_patron_code_ids
FROM DWIEntries e
JOIN DWIViewEntryAttributes a   ON a.EntryID = e.EntryID
LEFT JOIN DWIEntryDisplayOrder do ON do.EntryID = e.EntryID
WHERE EXISTS (
    SELECT 1 FROM DWIViewEntryAttributes obj
    WHERE obj.EntryID = e.EntryID
      AND obj.AttributeType = 'E-Source Object'
      AND obj.Value = 'ETarget'
)
AND EXISTS (
    SELECT 1 FROM DWIViewEntryAttributes org
    WHERE org.EntryID = e.EntryID
      AND org.AttributeType = 'OrganizationID'
      AND org.Value = '1'
)
GROUP BY e.EntryID, e.CommonName, do.ParentEntryID, do.DisplayOrder
HAVING MAX(CASE WHEN a.AttributeType = 'URL' THEN a.Value END) IS NOT NULL
ORDER BY do.DisplayOrder, e.CommonName;

-- --- Query B: category names (Org 1 only, "Old" categories kept) -----------
-- Imports keep "<Name> Old" categories in the CSV -- import_extract.py drops
-- them at load time so the filter is visible in code, not buried in SQL.
SELECT DISTINCT
    do.ParentEntryID    AS parent_entry_id,
    e.CommonName        AS category_name
FROM DWIEntryDisplayOrder do
JOIN DWIEntries e ON e.EntryID = do.ParentEntryID
WHERE do.ParentEntryID IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM DWIViewEntryAttributes org
    WHERE org.EntryID = e.EntryID
      AND org.AttributeType = 'OrganizationID'
      AND org.Value = '1'
  )
ORDER BY e.CommonName;

-- --- Query C: every Parameter row, long-form -------------------------------
-- Authoritative source for the launch parameters. Use this if Query A's
-- STUFF/FOR-XML aggregation looks suspicious for any entry.
SELECT
    p.EntryID    AS legacy_entry_id,
    p.Value      AS parameter
FROM DWIViewEntryAttributes p
WHERE p.AttributeType = 'Parameter'
  AND EXISTS (
    SELECT 1 FROM DWIViewEntryAttributes obj
    WHERE obj.EntryID = p.EntryID
      AND obj.AttributeType = 'E-Source Object'
      AND obj.Value = 'ETarget'
  )
  AND EXISTS (
    SELECT 1 FROM DWIViewEntryAttributes org
    WHERE org.EntryID = p.EntryID
      AND org.AttributeType = 'OrganizationID'
      AND org.Value = '1'
  )
ORDER BY p.EntryID;
