-- Database, schemas, warehouse, file formats and stages.
-- Run with: snow sql -c whales -f load/01_setup.sql
-- Safe to re-run: every statement is "if not exists".

CREATE WAREHOUSE IF NOT EXISTS WHALES_WH
  WAREHOUSE_SIZE = XSMALL
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;

CREATE DATABASE IF NOT EXISTS WHALES;
CREATE SCHEMA IF NOT EXISTS WHALES.RAW;
CREATE SCHEMA IF NOT EXISTS WHALES.MARTS;

USE WAREHOUSE WHALES_WH;
USE SCHEMA WHALES.RAW;

-- OBIS files carry a binary geometry column; reading it as text fails on invalid UTF-8.
CREATE FILE FORMAT IF NOT EXISTS PARQUET_FMT
  TYPE = PARQUET
  BINARY_AS_TEXT = FALSE;

CREATE FILE FORMAT IF NOT EXISTS TSV_GZ_FMT
  TYPE = CSV
  FIELD_DELIMITER = '\t'
  COMPRESSION = GZIP
  SKIP_HEADER = 1
  EMPTY_FIELD_AS_NULL = TRUE;

-- Both buckets are public and in us-east-1, so the stages carry no credentials.
CREATE STAGE IF NOT EXISTS OBIS_STAGE
  URL = 's3://obis-open-data/occurrence/'
  FILE_FORMAT = PARQUET_FMT;

CREATE STAGE IF NOT EXISTS INAT_STAGE
  URL = 's3://inaturalist-open-data/'
  FILE_FORMAT = TSV_GZ_FMT;
