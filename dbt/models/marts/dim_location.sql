-- One row per place a record can be: the four areas of the West Coast box outside Monterey Bay, and the bay
-- split by its nearest whale-watching harbor. Seven rows. The box is split at Point Conception (34.45 N), the
-- Oregon border (42 N) and the Columbia River (46.25 N), with the bay taken out of northern California;
-- fct_sighting puts each record in its area and finds its nearest harbor.

WITH coast_areas AS (
    SELECT
        column1 AS area,
        column2 AS area_order,
        column3 AS in_bay
    FROM VALUES
        ('WA/BC', 1, FALSE),
        ('OR', 2, FALSE),
        ('N CA outside the bay', 3, FALSE),
        ('Monterey Bay', 4, TRUE),
        ('S CA', 5, FALSE)
)

SELECT
    ROW_NUMBER() OVER (ORDER BY coast_areas.area_order, harbors.harbor) AS location_key,
    coast_areas.area,
    coast_areas.area_order,
    coast_areas.in_bay,
    harbors.harbor AS nearest_harbor,
    harbors.latitude AS harbor_latitude,
    harbors.longitude AS harbor_longitude
FROM coast_areas
-- (only the bay is split by harbor; the other areas get one row with no harbor)
LEFT JOIN {{ ref('harbors') }} AS harbors ON coast_areas.in_bay
