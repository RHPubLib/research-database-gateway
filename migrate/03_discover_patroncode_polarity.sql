-- ===========================================================================
-- eResources discovery -- STEP 3: is `PatronCodeID` an allow-list or a
-- block-list, and is there a polarity flag we missed?
-- ===========================================================================
-- The 02_extract pulled `AttributeType = 'PatronCodeID'` rows and surfaced
-- them as `allowed_patron_code_ids`. The data is inconsistent with that
-- label: Pronunciator's three codes (Non-Resident, MILibrary, Not Eligible)
-- only make sense as BLOCKED, while Ancestry's ten codes (Resident, Staff,
-- Business, Students, RCS, …) only make sense as ALLOWED. Either:
--   (a) Polaris uses a separate attribute / table to flag the polarity, OR
--   (b) Ancestry's data was entered backwards in Polaris and needs fixing
--       there, OR
--   (c) the same DWI attribute type carries different meanings depending
--       on something else we haven't looked at.
--
-- Each query below is independent; run them in LEAP/SSMS and paste the
-- output back for analysis.
-- ===========================================================================

-- --- Query A: every distinct AttributeType used by the 8 ETargets that
--              have PatronCodeID rows. If a polarity flag exists, it will
--              show up here as something we haven't extracted yet
--              (e.g. 'PatronCodeFilter', 'RestrictionMode', etc.).
WITH affected AS (
    SELECT DISTINCT EntryID
    FROM DWIViewEntryAttributes WITH (NOLOCK)
    WHERE AttributeType = 'PatronCodeID'
)
SELECT DISTINCT a.AttributeType, COUNT(*) AS row_count
FROM DWIViewEntryAttributes a WITH (NOLOCK)
JOIN affected x ON x.EntryID = a.EntryID
GROUP BY a.AttributeType
ORDER BY a.AttributeType;


-- --- Query B: every attribute row for Ancestry (CommonName like 'Ancestry%').
--              Side-by-side with the same dump for Pronunciator so we can
--              eyeball any difference between an "allow" entry and a "block"
--              entry.
SELECT
    e.EntryID,
    e.CommonName,
    a.AttributeType,
    a.Value
FROM DWIEntries e WITH (NOLOCK)
JOIN DWIViewEntryAttributes a WITH (NOLOCK) ON a.EntryID = e.EntryID
WHERE e.CommonName IN ('Ancestry.com', 'Pronunciator', 'Gale Presents: Udemy')
ORDER BY e.CommonName, a.AttributeType, a.Value;


-- --- Query C: does Polaris carry a separate AttributeType like
--              'ExcludedPatronCodeID' or 'AllowedPatronCodeID' that we
--              missed? Show every AttributeType that mentions 'Patron'
--              or 'Code' anywhere in Polaris -- not just on the 8 entries.
SELECT DISTINCT AttributeType
FROM DWIViewEntryAttributes WITH (NOLOCK)
WHERE AttributeType LIKE '%Patron%'
   OR AttributeType LIKE '%Code%'
   OR AttributeType LIKE '%Restrict%'
   OR AttributeType LIKE '%Allow%'
   OR AttributeType LIKE '%Block%'
   OR AttributeType LIKE '%Exclude%'
   OR AttributeType LIKE '%Filter%'
ORDER BY AttributeType;


-- --- Query D: belt-and-braces. List every Polaris table whose name
--              hints at eSource / DWI patron-code restrictions, so we
--              know we're not missing a sibling table outside DWIView*.
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND (TABLE_NAME LIKE '%DWI%'
       OR TABLE_NAME LIKE 'SA_DWI%'
       OR TABLE_NAME LIKE 'SA_OLP%'
       OR (TABLE_NAME LIKE '%PatronCode%' AND TABLE_NAME LIKE '%E%'))
ORDER BY TABLE_NAME;
