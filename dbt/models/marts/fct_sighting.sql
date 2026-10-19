-- One row per whale record on the West Coast: the star's main fact table.
-- Everything is read out of the record's JSON column. The record's position puts it in an area and, inside
-- Monterey Bay, finds its nearest whale-watching harbor and the distance to it; the area and harbor together
-- are its row in dim_location.

WITH whale_records AS (
    SELECT
        obis_occurrence.obis_id AS record_id,
        obis_occurrence.dataset_id,
        COALESCE(obis_occurrence.interpreted:species::STRING, obis_occurrence.interpreted:scientificName::STRING) AS taxon,
        obis_occurrence.interpreted:eventDate::STRING AS event_date,
        obis_occurrence.interpreted:decimalLatitude::FLOAT AS latitude,
        obis_occurrence.interpreted:decimalLongitude::FLOAT AS longitude
    FROM {{ source('raw', 'obis_occurrence') }} AS obis_occurrence
    -- (two absence records: someone looked and saw no whale)
    WHERE NOT obis_occurrence.absence
      AND NOT obis_occurrence.dropped
),

-- eventDate comes in a dozen shapes: a date, a date and time with or without a zone, and ranges.
-- The date is its first ten characters when they parse (a range keeps its start day; "2000-05" has none).
-- The hour is the clock hour as written: only about one timed record in seven states a zone (one in ten in the
-- bay), and nearly all of those are in Pacific offsets already. One record carries the Unix epoch as a placeholder date.
parsed_records AS (
    SELECT
        whale_records.record_id,
        whale_records.dataset_id,
        whale_records.taxon,
        whale_records.latitude,
        whale_records.longitude,
        whale_records.event_date LIKE '1969-12-31T16:00:00%' AS is_placeholder_date,
        IFF(is_placeholder_date, NULL, TRY_TO_DATE(LEFT(whale_records.event_date, 10))) AS observed_date,
        IFF(
            is_placeholder_date OR whale_records.event_date NOT LIKE '%T%',
            NULL,
            TRY_TO_NUMBER(SUBSTR(whale_records.event_date, 12, 2))
        ) AS local_hour,
        REGEXP_LIKE(whale_records.event_date, '.*T.*(Z|[+-][0-9]{2}:[0-9]{2})$') AS has_timezone,
        {{ in_bay('whale_records.latitude', 'whale_records.longitude') }} AS in_bay,
        -- (the areas dim_location lists: the names must match)
        CASE
            WHEN in_bay THEN 'Monterey Bay'
            WHEN whale_records.latitude < 34.45 THEN 'S CA'
            WHEN whale_records.latitude < 42 THEN 'N CA outside the bay'
            WHEN whale_records.latitude < 46.25 THEN 'OR'
            ELSE 'WA/BC'
        END AS area,
        -- (a position exactly on a 0.1 degree grid point was rounded, and can be several km off)
        ROUND(whale_records.latitude, 1) = whale_records.latitude
            AND ROUND(whale_records.longitude, 1) = whale_records.longitude AS is_rounded_position
    FROM whale_records
),

-- For each bay record, the harbor (a bay row of dim_location) with the shortest great-circle distance, and
-- that distance.
bay_nearest_harbor AS (
    SELECT
        parsed_records.record_id,
        MIN_BY(
            dim_location.nearest_harbor,
            HAVERSINE(
                parsed_records.latitude,
                parsed_records.longitude,
                dim_location.harbor_latitude,
                dim_location.harbor_longitude
            )
        ) AS nearest_harbor,
        MIN(
            HAVERSINE(
                parsed_records.latitude,
                parsed_records.longitude,
                dim_location.harbor_latitude,
                dim_location.harbor_longitude
            )
        ) AS km_to_harbor
    FROM parsed_records
    JOIN {{ ref('dim_location') }} AS dim_location ON dim_location.in_bay
    WHERE parsed_records.in_bay
    GROUP BY parsed_records.record_id
)

SELECT
    parsed_records.record_id,
    dim_date.date_key,
    dim_dataset.dataset_key,
    dim_species.species_key,
    dim_location.location_key,
    bay_nearest_harbor.km_to_harbor,
    CEIL(bay_nearest_harbor.km_to_harbor) AS km_band,
    parsed_records.is_rounded_position,
    parsed_records.latitude,
    parsed_records.longitude,
    -- (the map's grid cells, about 2.2 km a side, so the map draws one bubble per cell)
    ROUND(ROUND(parsed_records.longitude / 0.025) * 0.025, 3) AS map_lon,
    ROUND(ROUND(parsed_records.latitude / 0.02) * 0.02, 3) AS map_lat,
    map_lon || ', ' || map_lat AS map_cell,
    parsed_records.local_hour,
    parsed_records.has_timezone,
    parsed_records.local_hour BETWEEN 6 AND 19 AS is_daylight_hour,
    parsed_records.local_hour IN (10, 11) AS is_peak_hour,
    -- Monterey Bay Whale Watch's trips are at sea 9:00 to 13:00 and 13:30 to 16:30, so hours 13 and 16 count half.
    CASE
        WHEN parsed_records.local_hour BETWEEN 9 AND 12 OR parsed_records.local_hour IN (14, 15) THEN 1
        WHEN parsed_records.local_hour IN (13, 16) THEN 0.5
        WHEN parsed_records.local_hour IS NOT NULL THEN 0
    END AS trip_at_sea_weight
FROM parsed_records
JOIN {{ ref('dim_dataset') }} AS dim_dataset ON dim_dataset.dataset_id = parsed_records.dataset_id
JOIN {{ ref('dim_species') }} AS dim_species ON dim_species.scientific_name = parsed_records.taxon
LEFT JOIN {{ ref('dim_date') }} AS dim_date ON dim_date.date = parsed_records.observed_date
LEFT JOIN bay_nearest_harbor ON bay_nearest_harbor.record_id = parsed_records.record_id
JOIN {{ ref('dim_location') }} AS dim_location
  ON dim_location.area = parsed_records.area
 AND EQUAL_NULL(dim_location.nearest_harbor, bay_nearest_harbor.nearest_harbor)
