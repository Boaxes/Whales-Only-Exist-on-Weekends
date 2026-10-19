-- Every bay record has a nearest harbor between 0 and 100 km away; records outside the bay have none.
SELECT
    fct_sighting.record_id,
    dim_location.in_bay,
    dim_location.nearest_harbor,
    fct_sighting.km_to_harbor
FROM {{ ref('fct_sighting') }} AS fct_sighting
JOIN {{ ref('dim_location') }} AS dim_location ON dim_location.location_key = fct_sighting.location_key
WHERE (
        dim_location.in_bay
        AND (
            dim_location.nearest_harbor IS NULL
            OR fct_sighting.km_to_harbor IS NULL
            OR fct_sighting.km_to_harbor < 0
            OR fct_sighting.km_to_harbor > 100
        )
    )
   OR (
        NOT dim_location.in_bay
        AND (dim_location.nearest_harbor IS NOT NULL OR fct_sighting.km_to_harbor IS NOT NULL)
    )
