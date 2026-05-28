-- ===========================================================================
-- eResources migration — STEP 1: discover the Polaris DWI attribute layout
-- ===========================================================================
-- Run this against the Polaris SQL Server `Polaris` database (read-only) from
-- SSMS or sqlcmd. Its only purpose is to TELL YOU the real attribute names so
-- you can fill them into 02_extract_esources.sql — do not assume them.
--
-- The legacy classic-PAC eSource feature stores each database as a row in
-- DWIEntries, with its URL / description / etc. as rows in the DWI attribute
-- tables. DWIViewEntryAttributes is a flattened view of all three.
-- ===========================================================================

-- 1. Every attribute type in use, with how many entries carry it. Look here
--    for the URL attribute, a description attribute, and the "EM" tag.
SELECT AttributeType, COUNT(*) AS UsageCount
FROM DWIViewEntryAttributes
GROUP BY AttributeType
ORDER BY UsageCount DESC;

-- 2. A sample of real values for each attribute type, so you can see the
--    format (which one holds "http..." is the URL attribute).
SELECT TOP 300 EntryID, AttributeType, Value
FROM DWIViewEntryAttributes
ORDER BY EntryID, AttributeType;

-- 3. Anything that looks like the "EM" tag Derek was told about.
SELECT DISTINCT AttributeType
FROM DWIViewEntryAttributes
WHERE AttributeType LIKE '%EM%';

-- 4. How many distinct databases actually have a URL — this is the number the
--    import in step 3 must reconcile against.
SELECT COUNT(DISTINCT EntryID) AS EntriesWithUrl
FROM DWIViewEntryAttributes
WHERE AttributeType = 'URL';   -- adjust 'URL' if step 1 shows a different name

-- 5. Vendor logins. Confirm there is at most one row per EntryID; if an entry
--    has several (different OrgID/DBID), decide which OrgID to keep and add a
--    WHERE clause to the join in 02_extract_esources.sql.
SELECT EntryID, OrgID, DBID, UserName, Password
FROM SA_DWI_UserName_Password_Usage
ORDER BY EntryID;

-- 6. The category structure. Parent entries are themselves DWIEntries rows;
--    leaf databases point at them via DWIEntryDisplayOrder.ParentEntryID.
SELECT do.ParentEntryID, e.CommonName AS CategoryName, COUNT(*) AS ChildCount
FROM DWIEntryDisplayOrder do
JOIN DWIEntries e ON e.EntryID = do.ParentEntryID
GROUP BY do.ParentEntryID, e.CommonName
ORDER BY CategoryName;
