-- Every iNaturalist observation, all taxa, worldwide, into RAW.
-- Run with: snow sql -c whales -f load/03_inat.sql
-- The source is one 13.4 GB gzip file, which Snowflake reads on a single thread, so the
-- smallest warehouse is the right size. dbt keeps only the Monterey Bay box.

USE SCHEMA WHALES.RAW;
ALTER WAREHOUSE WHALES_WH SET WAREHOUSE_SIZE = XSMALL;

CREATE OR REPLACE TABLE INAT_OBSERVATIONS (
  observation_uuid STRING,
  observer_id NUMBER,
  latitude FLOAT,
  longitude FLOAT,
  positional_accuracy NUMBER,
  taxon_id NUMBER,
  quality_grade STRING,
  observed_on DATE,
  anomaly_score FLOAT,
  _source_file STRING,
  _loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ON_ERROR = CONTINUE so one malformed line does not throw away an hour's load;
-- the rows skipped are reported in the copy result and checked afterwards.
COPY INTO INAT_OBSERVATIONS
  (observation_uuid, observer_id, latitude, longitude, positional_accuracy,
   taxon_id, quality_grade, observed_on, anomaly_score, _source_file)
FROM (
  SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, METADATA$FILENAME
  FROM @INAT_STAGE/observations.csv.gz
)
FILE_FORMAT = (FORMAT_NAME = 'TSV_GZ_FMT')
ON_ERROR = CONTINUE;
