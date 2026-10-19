-- One row per day, from the earliest record (1925) to the last. A day can be a comparison day for one holiday
-- only: a holiday is always itself (Christmas and New Year's Day are a week apart), and a day a week after one
-- holiday and a week before the next goes to the earlier one.

WITH last_record_day AS (
    SELECT MAX(TRY_TO_DATE(LEFT(obis_occurrence.interpreted:eventDate::STRING, 10))) AS last_date
    FROM {{ source('raw', 'obis_occurrence') }} AS obis_occurrence
    WHERE NOT obis_occurrence.absence
      AND NOT obis_occurrence.dropped
),

calendar_days AS (
    SELECT DATEADD(DAY, ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, '1925-01-01'::DATE) AS date
    FROM TABLE(GENERATOR(ROWCOUNT => 40000))
    QUALIFY date <= (SELECT last_record_day.last_date FROM last_record_day)
),

inat_observers_per_day AS (
    SELECT
        inat_observations.observed_on AS date,
        COUNT(DISTINCT inat_observations.observer_id) AS inat_observers
    FROM {{ source('raw', 'inat_observations') }} AS inat_observations
    WHERE {{ in_bay('inat_observations.latitude', 'inat_observations.longitude') }}
    GROUP BY inat_observations.observed_on
),

-- Every day that could stand in a holiday's comparison, with how far it is from its holiday.
holiday_candidates AS (
    SELECT
        holidays.holiday_date AS date,
        'Holiday' AS holiday_comparison,
        holidays.name AS compared_holiday,
        holidays.holiday_date,
        0 AS days_from_holiday
    FROM {{ ref('holidays') }} AS holidays

    UNION ALL

    SELECT
        DATEADD(DAY, week_shifts.shift_days, holidays.holiday_date) AS date,
        'Same Weekday' AS holiday_comparison,
        holidays.name AS compared_holiday,
        holidays.holiday_date,
        7 AS days_from_holiday
    FROM {{ ref('holidays') }} AS holidays
    CROSS JOIN (SELECT column1 AS shift_days FROM VALUES (-7), (7)) AS week_shifts

    UNION ALL

    SELECT
        DATEADD(DAY, weekend_days.weekday_number - DAYOFWEEKISO(holidays.holiday_date), holidays.holiday_date) AS date,
        'Weekend' AS holiday_comparison,
        holidays.name AS compared_holiday,
        holidays.holiday_date,
        weekend_days.weekday_number - DAYOFWEEKISO(holidays.holiday_date) AS days_from_holiday
    FROM {{ ref('holidays') }} AS holidays
    CROSS JOIN (SELECT column1 AS weekday_number FROM VALUES (6), (7)) AS weekend_days
),

-- A day that is a candidate for two holidays goes to the nearer one, then the earlier one.
holiday_assignment AS (
    SELECT
        holiday_candidates.date,
        holiday_candidates.holiday_comparison,
        holiday_candidates.compared_holiday,
        holiday_candidates.holiday_date AS compared_holiday_date
    FROM holiday_candidates
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY holiday_candidates.date
        ORDER BY holiday_candidates.days_from_holiday, holiday_candidates.holiday_date
    ) = 1
)

SELECT
    TO_NUMBER(TO_CHAR(calendar_days.date, 'YYYYMMDD')) AS date_key,
    calendar_days.date,
    DAYNAME(calendar_days.date) AS weekday_name,
    DAYOFWEEKISO(calendar_days.date) AS weekday_number,
    -- Every weekend ratio sets the weekend against Tuesday to Thursday: Mondays and Fridays are left out,
    -- because long weekends and holidays blur them.
    DAYOFWEEKISO(calendar_days.date) IN (6, 7) AS is_weekend,
    DAYOFWEEKISO(calendar_days.date) IN (2, 3, 4) AS is_midweek,
    YEAR(calendar_days.date) AS year,
    DATE_TRUNC(MONTH, calendar_days.date) AS month_start,
    holiday_assignment.holiday_comparison,
    holiday_assignment.compared_holiday,
    holiday_assignment.compared_holiday_date,
    -- (15 March to 15 June)
    (MONTH(calendar_days.date) = 3 AND DAY(calendar_days.date) >= 15)
        OR MONTH(calendar_days.date) IN (4, 5)
        OR (MONTH(calendar_days.date) = 6 AND DAY(calendar_days.date) <= 15) AS in_spring_window,
    calendar_days.date BETWEEN '{{ var("hydrophone_window")[0] }}' AND '{{ var("hydrophone_window")[1] }}'
        AS in_hydrophone_window,
    COALESCE(inat_observers_per_day.inat_observers, 0) AS inat_observers
FROM calendar_days
LEFT JOIN holiday_assignment ON holiday_assignment.date = calendar_days.date
LEFT JOIN inat_observers_per_day ON inat_observers_per_day.date = calendar_days.date
