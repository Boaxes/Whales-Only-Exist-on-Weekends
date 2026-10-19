-- Whale records into RAW: every cetacean record in the West Coast box.
-- Reads the whole OBIS archive (about 97 GB) once, inside Snowflake; nothing is downloaded.
-- Run with: snow sql -c whales -f load/02_obis.sql
-- Cetacea is WoRMS infraorder 2688.
-- Dropped and absence records are kept here and filtered in dbt.

USE SCHEMA WHALES.RAW;

-- A larger warehouse costs the same in total for a scan this parallel, and finishes sooner.
ALTER WAREHOUSE WHALES_WH SET WAREHOUSE_SIZE = MEDIUM;

CREATE OR REPLACE TABLE OBIS_OCCURRENCE AS
SELECT
  $1:_id::STRING AS obis_id,
  $1:dataset_id::STRING AS dataset_id,
  $1:interpreted AS interpreted,
  $1:flags AS flags,
  $1:dropped::BOOLEAN AS dropped,
  $1:absence::BOOLEAN AS absence,
  METADATA$FILENAME AS _source_file,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM @OBIS_STAGE (FILE_FORMAT => 'PARQUET_FMT', PATTERN => '.*\\.parquet')
WHERE $1:interpreted:infraorderid::INT = 2688
  AND $1:interpreted:decimalLatitude::FLOAT BETWEEN 32 AND 49.5
  AND $1:interpreted:decimalLongitude::FLOAT BETWEEN -130 AND -116;

ALTER WAREHOUSE WHALES_WH SET WAREHOUSE_SIZE = XSMALL;
