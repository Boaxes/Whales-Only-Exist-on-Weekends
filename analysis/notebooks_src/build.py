"""The six analysis notebooks, one per claim.

    uv run python analysis/notebooks_src/build.py

Writes analysis/0*.ipynb (the Snowflake Workspace notebooks), then the same cells as marimo notebooks, which it
runs once against Snowflake and exports to docs/notebooks/ as static pages with their results.
"""
import marimo_nb
from nb import md, sql, write

NOTEBOOKS = []

# ---------------------------------------------------------------------------------------------------------
NOTEBOOKS.append(('01_weekends.ipynb', [
    md('intro', '''
        # Whales Are Seen More on Weekends

        Whales do not know what day it is. If the public record (Happywhale and iNaturalist) only recorded
        whales, a Saturday would look like a Tuesday. This notebook measures how far it does not, and checks
        the result against the hydrophones, which recorded on most days.

        **Weekend ratio:** records on an average weekend day ÷ records on an average Tuesday-to-Thursday day,
        that is (Sat + Sun) / 2 over (Tue + Wed + Thu) / 3, from `dim_date.is_weekend` and `is_midweek`. Monday
        and Friday are left out, because long weekends and holidays blur them; the ratio against all five
        weekdays is shown beside it. A source with no weekly rhythm scores about 1.
    '''),
    md('step1', '## Public Sightings on Each Day of the Week\nPublic records inside the Monterey Bay box, counted by weekday.'),
    sql('weekday_counts', '''
        SELECT
            dim_date.weekday_number,
            dim_date.weekday_name,
            COUNT(*) AS public_records
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
          AND dim_dataset.kind = 'public'
        GROUP BY dim_date.weekday_number, dim_date.weekday_name
        ORDER BY dim_date.weekday_number
    '''),
    md('step2', '## The Weekend Ratio for Every Kind of Source'),
    sql('ratio_by_kind', '''
        SELECT
            dim_dataset.kind,
            COUNT(*) AS records,
            ROUND(
                (COUNT_IF(dim_date.is_weekend) / 2) / NULLIF(COUNT_IF(dim_date.is_midweek) / 3, 0),
                2
            ) AS weekend_ratio,
            ROUND(
                (COUNT_IF(dim_date.is_weekend) / 2) / NULLIF(COUNT_IF(NOT dim_date.is_weekend) / 5, 0),
                2
            ) AS weekend_ratio_against_all_weekdays
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
        GROUP BY dim_dataset.kind
        ORDER BY weekend_ratio DESC
    '''),
    md('step2b', '''
        ## What Sits Behind the Survey and Other Ratios
        The same ratio for each survey and "other" dataset in the bay, with the number of days it has records on.
    '''),
    sql('kinds_by_dataset', '''
        SELECT
            dim_dataset.kind,
            dim_dataset.title,
            COUNT(*) AS records,
            COUNT(DISTINCT fct_sighting.date_key) AS days,
            ROUND(
                (COUNT_IF(dim_date.is_weekend) / 2) / NULLIF(COUNT_IF(dim_date.is_midweek) / 3, 0),
                2
            ) AS weekend_ratio
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
          AND dim_dataset.kind IN ('survey', 'other')
        GROUP BY dim_dataset.kind, dim_dataset.title
        ORDER BY dim_dataset.kind, records DESC
    '''),
    md('step3', '''
        ## How Sure Is the Public Ratio?
        A few unusually busy weekends could carry the ratio on their own. So the public records are grouped
        into Monday-to-Sunday weeks, the same number of weeks is drawn at random with replacement 2,000 times,
        and the ratio is recomputed each time. The middle 95% of those ratios is the range.
        `GENERATOR` makes the 2,000 replicates, and a `HASH` of the replicate and the draw picks each week, so
        every run draws the same weeks and gives the same range. (`SAMPLE` cannot do this: it draws without
        replacement, and Snowflake's seeded `RANDOM` does not repeat its draws from one run to the next.)
    '''),
    sql('weekly_resample', '''
        WITH weekly_counts AS (
            SELECT
                DATEADD(DAY, 1 - dim_date.weekday_number, dim_date.date) AS week_start,
                COUNT_IF(dim_date.is_weekend) AS weekend_records,
                COUNT_IF(dim_date.is_midweek) AS midweek_records
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_location.in_bay
              AND dim_dataset.kind = 'public'
            GROUP BY week_start
        ),

        numbered_weeks AS (
            SELECT
                ROW_NUMBER() OVER (ORDER BY week_start) AS week_number,
                COUNT(*) OVER () AS total_weeks,
                weekend_records,
                midweek_records
            FROM weekly_counts
        ),

        replicates AS (
            SELECT SEQ4() AS replicate
            FROM TABLE(GENERATOR(ROWCOUNT => 2000))
        ),

        -- Each replicate draws as many weeks as there are, at random and with replacement.
        resample_draws AS (
            SELECT
                replicates.replicate,
                1 + MOD(
                    ABS(HASH(replicates.replicate, numbered_weeks.week_number, 20261016)),
                    numbered_weeks.total_weeks
                ) AS week_number
            FROM replicates
            CROSS JOIN numbered_weeks
        ),

        resampled_ratios AS (
            SELECT
                resample_draws.replicate,
                (SUM(numbered_weeks.weekend_records) / 2)
                / NULLIF(SUM(numbered_weeks.midweek_records) / 3, 0) AS weekend_ratio
            FROM resample_draws
            JOIN numbered_weeks ON numbered_weeks.week_number = resample_draws.week_number
            GROUP BY resample_draws.replicate
        )

        SELECT
            (SELECT MAX(total_weeks) FROM numbered_weeks) AS weeks,
            ROUND(PERCENTILE_CONT(0.025) WITHIN GROUP (ORDER BY weekend_ratio), 2) AS range_low,
            ROUND(PERCENTILE_CONT(0.975) WITHIN GROUP (ORDER BY weekend_ratio), 2) AS range_high
        FROM resampled_ratios
    '''),
    md('step4', '''
        ## The Control: Did the Hydrophones Hear More Whales on Weekends?
        NOAA's SanctSound hydrophones in the bay recorded on most days from November 2018 to June 2021
        (`in_hydrophone_window`). Their record counts mix very different instruments, so this counts **days
        with at least one detection** and applies the same ratio to days.
    '''),
    sql('hydrophone_days', '''
        WITH window_days AS (
            SELECT
                dim_date.date_key,
                dim_date.is_weekend,
                dim_date.is_midweek
            FROM dim_date
            WHERE dim_date.in_hydrophone_window
        ),

        heard_days AS (
            SELECT DISTINCT fct_sighting.date_key
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_location.in_bay
              AND dim_dataset.kind = 'hydrophone'
        )

        SELECT
            COUNT(*) AS days_recording,
            COUNT(heard_days.date_key) AS days_heard,
            ROUND(days_heard / days_recording, 2) AS share_of_days_heard,
            ROUND(
                (COUNT_IF(window_days.is_weekend AND heard_days.date_key IS NOT NULL)
                    / COUNT_IF(window_days.is_weekend))
                / NULLIF(
                    COUNT_IF(window_days.is_midweek AND heard_days.date_key IS NOT NULL)
                        / COUNT_IF(window_days.is_midweek),
                    0
                ),
                2
            ) AS detection_day_ratio
        FROM window_days
        LEFT JOIN heard_days ON heard_days.date_key = window_days.date_key
    '''),
    md('step4b', '''
        ## How Sure Is the Hydrophone Ratio?
        The same resampling as for the public ratio: the weeks of the window drawn at random with replacement
        2,000 times, and the share of weekend days heard over the share of midweek days heard each time.
    '''),
    sql('hydrophone_resample', '''
        WITH heard_days AS (
            SELECT DISTINCT fct_sighting.date_key
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_location.in_bay
              AND dim_dataset.kind = 'hydrophone'
        ),

        weekly_counts AS (
            SELECT
                DATEADD(DAY, 1 - dim_date.weekday_number, dim_date.date) AS week_start,
                COUNT_IF(dim_date.is_weekend) AS weekend_days,
                COUNT_IF(dim_date.is_weekend AND heard_days.date_key IS NOT NULL) AS weekend_days_heard,
                COUNT_IF(dim_date.is_midweek) AS midweek_days,
                COUNT_IF(dim_date.is_midweek AND heard_days.date_key IS NOT NULL) AS midweek_days_heard
            FROM dim_date
            LEFT JOIN heard_days ON heard_days.date_key = dim_date.date_key
            WHERE dim_date.in_hydrophone_window
            GROUP BY week_start
        ),

        numbered_weeks AS (
            SELECT
                ROW_NUMBER() OVER (ORDER BY week_start) AS week_number,
                COUNT(*) OVER () AS total_weeks,
                weekend_days,
                weekend_days_heard,
                midweek_days,
                midweek_days_heard
            FROM weekly_counts
        ),

        replicates AS (
            SELECT SEQ4() AS replicate
            FROM TABLE(GENERATOR(ROWCOUNT => 2000))
        ),

        resample_draws AS (
            SELECT
                replicates.replicate,
                1 + MOD(
                    ABS(HASH(replicates.replicate, numbered_weeks.week_number, 20261016)),
                    numbered_weeks.total_weeks
                ) AS week_number
            FROM replicates
            CROSS JOIN numbered_weeks
        ),

        resampled_ratios AS (
            SELECT
                resample_draws.replicate,
                (SUM(numbered_weeks.weekend_days_heard) / NULLIF(SUM(numbered_weeks.weekend_days), 0))
                / NULLIF(SUM(numbered_weeks.midweek_days_heard) / NULLIF(SUM(numbered_weeks.midweek_days), 0), 0)
                    AS detection_day_ratio
            FROM resample_draws
            JOIN numbered_weeks ON numbered_weeks.week_number = resample_draws.week_number
            GROUP BY resample_draws.replicate
        )

        SELECT
            (SELECT MAX(total_weeks) FROM numbered_weeks) AS weeks,
            ROUND(PERCENTILE_CONT(0.025) WITHIN GROUP (ORDER BY detection_day_ratio), 2) AS range_low,
            ROUND(PERCENTILE_CONT(0.975) WITHIN GROUP (ORDER BY detection_day_ratio), 2) AS range_high
        FROM resampled_ratios
    '''),
    md('step5', '''
        ## The Public Ratio Over the Same Days
        The public weekend ratio inside the hydrophone window, so the two are compared over the same days.
    '''),
    sql('public_in_window', '''
        SELECT
            COUNT(*) AS public_records,
            ROUND(
                (COUNT_IF(dim_date.is_weekend) / 2) / NULLIF(COUNT_IF(dim_date.is_midweek) / 3, 0),
                2
            ) AS weekend_ratio
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
          AND dim_dataset.kind = 'public'
          AND dim_date.in_hydrophone_window
    '''),
    md('result', '''
        ## Result
        A weekend day carries **1.52×** the public sightings of a Tuesday-to-Thursday day (95% range 1.42 to 1.63,
        from 1,106 resampled weeks), and 1.37× those of an average weekday. For the hydrophones, a weekend day was
        0.97× as likely as a midweek day to have a whale heard (95% range 0.94 to 1.01), while over the same 941 days
        a weekend day still carried 1.31× the public sightings of a midweek day. Ship and aircraft surveys show no
        weekend rise either: a weekend day carries 0.44× the survey records of a midweek day.
    '''),
    md('limits', '''
        ## Limits
        * The hydrophones heard whales on 858 of the 941 days in their window, so their ratio has little room to
          rise. The window is calendar days, so a day they were out of the water counts as not heard, and weekend
          boat noise could hide some calls.
        * The survey figures rest on about 150 survey days from a handful of programmes, mostly 1980s flights.
          "Other" is mostly two weekday-only shore studies of the gray whale migration, in 2014 and 2015.
        * Each record counts as one sighting, though one boat trip can log several.
    '''),
]))

# ---------------------------------------------------------------------------------------------------------
NOTEBOOKS.append(('02_holidays.ipynb', [
    md('intro', '''
        # A Holiday Is Most of a Weekend

        If public sightings follow people's days off rather than whales, a federal holiday (all fall on
        weekdays, on their observed dates) should look like a weekend day. `dim_date.holiday_comparison` marks
        each holiday, the same weekday one week before and after it, and the Saturday and Sunday of its week;
        `compared_holiday` and `compared_holiday_date` say which holiday a day belongs to, so each holiday is
        set against its own comparison days. When one of those days is a holiday itself (Christmas and New
        Year's Day are a week apart), the other day stands alone.
    '''),
    md('step1', '''
        ## Each Holiday Beside Its Own Days
        One row per holiday: its public records, and the average over its same-weekday days and its weekend
        days. Days with no public record count as zero.
    '''),
    sql('holiday_compare', '''
        CREATE OR REPLACE TEMPORARY VIEW holiday_compare AS
        WITH bay_public_sightings AS (
            SELECT
                fct_sighting.date_key,
                fct_sighting.record_id
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_location.in_bay
              AND dim_dataset.kind = 'public'
        ),

        comparison_days AS (
            SELECT
                dim_date.date_key,
                dim_date.holiday_comparison,
                dim_date.compared_holiday,
                dim_date.compared_holiday_date,
                COUNT(bay_public_sightings.record_id) AS public_records
            FROM dim_date
            LEFT JOIN bay_public_sightings ON bay_public_sightings.date_key = dim_date.date_key
            WHERE dim_date.holiday_comparison IS NOT NULL
            GROUP BY
                dim_date.date_key,
                dim_date.holiday_comparison,
                dim_date.compared_holiday,
                dim_date.compared_holiday_date
        )

        SELECT
            compared_holiday_date AS holiday_date,
            compared_holiday AS holiday,
            SUM(IFF(holiday_comparison = 'Holiday', public_records, NULL)) AS holiday_records,
            AVG(IFF(holiday_comparison = 'Same Weekday', public_records, NULL))
                AS same_weekday_records,
            AVG(IFF(holiday_comparison = 'Weekend', public_records, NULL)) AS weekend_records
        FROM comparison_days
        GROUP BY compared_holiday_date, compared_holiday
        HAVING holiday_records IS NOT NULL
           AND same_weekday_records IS NOT NULL
    '''),
    md('step2', '''
        ## The Holiday Ratio
        Holiday records ÷ same-weekday records, summed before dividing, so a busy Memorial Day counts for more
        than a quiet Columbus Day.
    '''),
    sql('holiday_ratio', '''
        SELECT
            COUNT(*) AS holidays,
            ROUND(AVG(same_weekday_records), 1) AS same_weekday_records_per_day,
            ROUND(AVG(holiday_records), 1) AS holiday_records_per_day,
            ROUND(AVG(weekend_records), 1) AS weekend_records_per_day,
            ROUND(SUM(holiday_records) / SUM(same_weekday_records), 2) AS holiday_ratio,
            ROUND(SUM(weekend_records) / SUM(same_weekday_records), 2) AS weekend_ratio
        FROM holiday_compare
    '''),
    md('step3', '## Each Holiday on Its Own'),
    sql('ratio_by_holiday', '''
        SELECT
            holiday,
            COUNT(*) AS years,
            ROUND(SUM(holiday_records) / SUM(same_weekday_records), 2) AS holiday_ratio
        FROM holiday_compare
        GROUP BY holiday
        ORDER BY holiday_ratio
    '''),
    md('step4', '''
        ## How Sure? Resample Holidays
        The same holidays drawn at random with replacement 2,000 times, each with its own comparison days,
        and the ratio recomputed each time.
    '''),
    sql('holiday_resample', '''
        WITH numbered_holidays AS (
            SELECT
                ROW_NUMBER() OVER (ORDER BY holiday_date) AS holiday_number,
                COUNT(*) OVER () AS total_holidays,
                holiday_records,
                same_weekday_records
            FROM holiday_compare
        ),

        replicates AS (
            SELECT SEQ4() AS replicate
            FROM TABLE(GENERATOR(ROWCOUNT => 2000))
        ),

        -- Each replicate draws as many holidays as there are, at random and with replacement.
        resample_draws AS (
            SELECT
                replicates.replicate,
                1 + MOD(
                    ABS(HASH(replicates.replicate, numbered_holidays.holiday_number, 20261016)),
                    numbered_holidays.total_holidays
                ) AS holiday_number
            FROM replicates
            CROSS JOIN numbered_holidays
        ),

        resampled_ratios AS (
            SELECT
                resample_draws.replicate,
                SUM(numbered_holidays.holiday_records)
                    / SUM(numbered_holidays.same_weekday_records) AS holiday_ratio
            FROM resample_draws
            JOIN numbered_holidays
              ON numbered_holidays.holiday_number = resample_draws.holiday_number
            GROUP BY resample_draws.replicate
        )

        SELECT
            ROUND(PERCENTILE_CONT(0.025) WITHIN GROUP (ORDER BY holiday_ratio), 2) AS range_low,
            ROUND(PERCENTILE_CONT(0.975) WITHIN GROUP (ORDER BY holiday_ratio), 2) AS range_high
        FROM resampled_ratios
    '''),
    md('result', '''
        ## Result
        A weekday holiday carries **1.30×** the public sightings of the same weekday one week before and after
        (95% range 1.11 to 1.54, over the 171 holidays since 2010 that the records reach). That is 9.8 a day on the
        holiday, 7.5 on those weekdays and 10.7 on the weekend of the holiday's week, so a holiday goes
        (9.8 - 7.5) / (10.7 - 7.5), about seven tenths, of the way from a weekday to a weekend. Christmas Day
        gets only 0.27× the public sightings of its comparison weekdays, and Martin Luther King Jr. Day the most,
        4.05× theirs.
    '''),
    md('limits', '''
        ## Limits
        * The 95% range runs from a quarter of the way to a weekend to past a full one.
    '''),
]))

# ---------------------------------------------------------------------------------------------------------
NOTEBOOKS.append(('03_timetable.ipynb', [
    md('intro', '''
        # Sightings Follow the Boat Timetable

        If the public record is a record of boat trips, sightings should bunch up in the hours the boats are
        at sea, not spread across daylight the way whales are. Monterey Bay Whale Watch runs a morning trip
        from 9:00 (3.5 to 4 hours) and an afternoon trip from 13:30 (3 hours)
        ([schedule](https://montereybaywhalewatch.com/schedule/), read 16 October 2026).

        `local_hour` is the clock hour written on each record. Only about one timed record in ten states a
        time zone (`has_timezone`), nearly always a Pacific offset, so hours are read as local time and the
        share for zone-stating records alone is reported beside the main figure.
    '''),
    md('step1', '## Timed Public Sightings in Each Hour'),
    sql('by_hour', '''
        SELECT
            fct_sighting.local_hour,
            COUNT(*) AS public_records,
            COUNT_IF(fct_sighting.has_timezone) AS zone_known_records
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
          AND dim_dataset.kind = 'public'
          AND fct_sighting.local_hour IS NOT NULL
        GROUP BY fct_sighting.local_hour
        ORDER BY fct_sighting.local_hour
    '''),
    md('step2', '''
        ## The Shares
        Every share is of sightings logged in daylight, 6:00 to 19:59 (`is_daylight_hour`).
        * **10:00 to 11:59** (`is_peak_hour`): the two peak hours, for all daylight sightings and for those that
          state a time zone. Spread evenly over the 14 daylight hours, two hours would hold 14%.
        * **While a trip is at sea** (`trip_at_sea_weight`): 9:00 to 13:00 and 13:30 to 16:30. A trip is out for
          half of hours 13 and 16, so a sighting in those hours counts half. The 7 hours are half of daylight, so
          an even spread would put 50% of sightings in them.
    '''),
    sql('shares', '''
        SELECT
            COUNT(*) AS daylight_records,
            ROUND(COUNT_IF(fct_sighting.is_peak_hour) / daylight_records, 3) AS share_10_to_12,
            ROUND(SUM(fct_sighting.trip_at_sea_weight) / daylight_records, 3) AS share_while_trips_at_sea,
            COUNT_IF(fct_sighting.has_timezone) AS zone_known_records,
            ROUND(
                COUNT_IF(fct_sighting.is_peak_hour AND fct_sighting.has_timezone) / zone_known_records,
                3
            ) AS share_10_to_12_zone_known
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
          AND dim_dataset.kind = 'public'
          AND fct_sighting.is_daylight_hour
    '''),
    md('result', '''
        ## Result
        Of public sightings logged in daylight, **44%** fall in two hours, 10:00 to 11:59, against 14% if spread
        evenly, and 89% while a scheduled trip is at sea, against 50%. Records that state a time zone give 38% for
        the two peak hours.
    '''),
    md('limits', '''
        ## Limits
        * People are out most at mid-morning anyway, so the two peak hours alone overstate the timetable; the
          share while trips are at sea is the firmer measure.
        * The trip times are one operator's current schedule, applied to twenty years and three harbors.
        * Nine timed records in ten have no time zone.
    '''),
]))

# ---------------------------------------------------------------------------------------------------------
NOTEBOOKS.append(('04_harbors.ipynb', [
    md('intro', '''
        # Sightings Stay Close to the Harbors

        A whale-watching trip lasts three or four hours, so it can only reach so far. If the public record is
        a record of trips, sightings should crowd close to Monterey, Moss Landing and Santa Cruz. The
        baseline is ship and aircraft surveys (`kind = 'survey'`), which go where their route sends them.

        `km_to_harbor` is the great-circle distance to the nearest of the three, worked out in dbt, and
        `dim_location.nearest_harbor` names it. The bay is the box 36.4 to 37.1 N, 122.6 to 121.7 W. A 0.1° grid
        step is about 11 km, and a record on an exact grid point (`is_rounded_position`) was rounded to it, so each
        group is shown with finer positions only and with all its records.
    '''),
    md('step1', '## How Far Out Do the Records Go?\nThe distance within which 50, 75, 90 and 99% of each group falls.'),
    sql('percentiles', '''
        WITH bay_records AS (
            SELECT
                dim_dataset.kind,
                fct_sighting.date_key,
                fct_sighting.km_to_harbor,
                fct_sighting.is_rounded_position
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_location.in_bay
        ),

        record_groups AS (
            SELECT 'Public, finer positions' AS record_group, date_key, km_to_harbor
            FROM bay_records
            WHERE kind = 'public' AND NOT is_rounded_position
            UNION ALL
            SELECT 'Public, all records' AS record_group, date_key, km_to_harbor
            FROM bay_records
            WHERE kind = 'public'
            UNION ALL
            SELECT 'Surveys, finer positions' AS record_group, date_key, km_to_harbor
            FROM bay_records
            WHERE kind = 'survey' AND NOT is_rounded_position
            UNION ALL
            SELECT 'Surveys, all records' AS record_group, date_key, km_to_harbor
            FROM bay_records
            WHERE kind = 'survey'
        )

        SELECT
            record_group,
            COUNT(*) AS records,
            COUNT(DISTINCT date_key) AS days,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY km_to_harbor), 1) AS median_km,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY km_to_harbor), 1)
                AS km_75th_percentile,
            ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY km_to_harbor), 1)
                AS km_90th_percentile,
            ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY km_to_harbor), 1)
                AS km_99th_percentile
        FROM record_groups
        GROUP BY record_group
        ORDER BY median_km
    '''),
    md('step2', '## Which Harbor?\nShare of public sightings by the harbor they are nearest to.'),
    sql('by_harbor', '''
        SELECT
            dim_location.nearest_harbor,
            COUNT(*) AS public_records,
            ROUND(COUNT(*) / SUM(COUNT(*)) OVER (), 3) AS share_of_public_records
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
          AND dim_dataset.kind = 'public'
        GROUP BY dim_location.nearest_harbor
        ORDER BY public_records DESC
    '''),
    md('result', '''
        ## Result
        Half of public sightings are within **10.8 km** of a harbor (10.4 km with precise positions only), and 90%
        within 18.1 km. Half of ship and aircraft survey records are beyond 25.2 km (25.3 km). Moss Landing is the
        harbor nearest to most public sightings, 47% of them.
    '''),
    md('limits', '''
        ## Limits
        * The survey figures depend partly on how far the bay box reaches, and come from only 150 survey days.
        * Moss Landing sits at the head of the Monterey submarine canyon, where whales feed, and survey routes are
          set in advance, so not all of the gap is people.
        * A record on an exact 0.1° grid point was rounded and can be several km off.
    '''),
]))

# ---------------------------------------------------------------------------------------------------------
NOTEBOOKS.append(('05_lockdown.ipynb', [
    md('intro', '''
        # The Whales Stayed When the Boats Stopped

        Whale-watching boats stopped in spring 2020: Monterey Bay Whale Watch ran no public trips in late
        March, April and May, and resumed on 13 June
        ([sightings log](https://montereybaywhalewatch.com/sightings/slst2006/), read 16 October 2026).
        If the public record measures whales, it should hold steady; if it measures boats, it should collapse.
        The hydrophones kept recording either way, and `dim_date.inat_observers` shows whether people kept
        recording wildlife at all.

        The window is 15 March to 15 June (93 days, `in_spring_window`), compared across 2019, 2020 and 2021.
    '''),
    md('step1', '## Three Springs Compared'),
    sql('springs', '''
        WITH spring_days AS (
            SELECT
                dim_date.date_key,
                dim_date.year,
                dim_date.inat_observers,
                dim_date.in_hydrophone_window
            FROM dim_date
            WHERE dim_date.in_spring_window
              AND dim_date.year BETWEEN 2019 AND 2021
        ),

        public_records_per_day AS (
            SELECT
                fct_sighting.date_key,
                COUNT(*) AS public_records
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_location.in_bay
              AND dim_dataset.kind = 'public'
            GROUP BY fct_sighting.date_key
        ),

        hydrophone_days AS (
            SELECT DISTINCT fct_sighting.date_key
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_location.in_bay
              AND dim_dataset.kind = 'hydrophone'
        ),

        spring_totals AS (
            SELECT
                spring_days.year,
                COUNT(*) AS days,
                SUM(COALESCE(public_records_per_day.public_records, 0)) AS public_records,
                COUNT_IF(spring_days.in_hydrophone_window) AS days_recording,
                COUNT(hydrophone_days.date_key) AS days_heard,
                ROUND(AVG(spring_days.inat_observers), 1) AS inat_observers_per_day
            FROM spring_days
            LEFT JOIN public_records_per_day
              ON public_records_per_day.date_key = spring_days.date_key
            LEFT JOIN hydrophone_days ON hydrophone_days.date_key = spring_days.date_key
            GROUP BY spring_days.year
        )

        SELECT
            TO_VARCHAR(year) AS year,
            days,
            public_records,
            days_recording,
            days_heard,
            inat_observers_per_day,
            ROUND(public_records / FIRST_VALUE(public_records) OVER (ORDER BY year) - 1, 3)
                AS public_records_change_from_2019,
            ROUND(
                public_records / AVG(IFF(year IN (2019, 2021), public_records, NULL)) OVER () - 1,
                3
            ) AS public_records_change_from_2019_2021_average,
            ROUND(days_heard / days_recording, 2) AS share_of_days_heard
        FROM spring_totals
        ORDER BY year
    '''),
    md('step2', '''
        ## Every Spring Since 2010
        Public sightings in the same window each year, to show how far an ordinary spring moves.
    '''),
    sql('every_spring', '''
        SELECT
            TO_VARCHAR(dim_date.year) AS year,
            COUNT(*) AS public_records
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        WHERE dim_location.in_bay
          AND dim_dataset.kind = 'public'
          AND dim_date.in_spring_window
          AND dim_date.year BETWEEN 2010 AND 2025
        GROUP BY dim_date.year
        ORDER BY dim_date.year
    '''),
    md('result', '''
        ## Result
        In spring 2020 public sightings fell **79%** against spring 2019 (1,253 to 266), and 77% against the
        average of 2019 and 2021. Every other spring from 2018 to 2025 had at least 1,070, and 266 is the lowest
        since 2013. The hydrophones heard whales on 92 of the 93 days in their recording window, against 60 of 93
        in 2019 and 80 of 90 in 2021, and iNaturalist users kept recording wildlife around the bay.
    '''),
    md('limits', '''
        ## Limits
        * Beaches and harbors closed as well as the boats.
        * Ordinary springs swing widely too (2,560 in 2022, 1,191 in 2023).
        * Days heard show whales were present, not how many. A quieter ocean may have helped the hydrophones hear,
          and a day they were out of the water counts as not heard.
        * iNaturalist was growing anyway (67.6 observers a day in spring 2021).
    '''),
]))

# ---------------------------------------------------------------------------------------------------------
NOTEBOOKS.append(('06_coast.ipynb', [
    md('intro', '''
        # The Weekend Holds Along the Coast

        Monterey Bay has one busy whale-watching fleet. Does the weekend pattern show up along the rest of the
        West Coast too? `dim_location.area` splits the box at Point Conception (34.45 N), the Oregon border
        (42 N) and the Columbia River (46.25 N), with Monterey Bay taken out of northern California. The
        weekend ratio is the same as in notebook 01.
    '''),
    md('step1', '## Weekend Ratio for Each Area and Kind of Source\nAreas north to south; kinds with at least 200 records.'),
    sql('ratio_by_area', '''
        SELECT
            dim_location.area,
            dim_dataset.kind,
            COUNT(*) AS records,
            ROUND(
                (COUNT_IF(dim_date.is_weekend) / 2) / NULLIF(COUNT_IF(dim_date.is_midweek) / 3, 0),
                2
            ) AS weekend_ratio
        FROM fct_sighting
        JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
        JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
        JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
        GROUP BY dim_location.area, dim_location.area_order, dim_dataset.kind
        HAVING COUNT(*) >= 200
        ORDER BY dim_location.area_order, dim_dataset.kind
    '''),
    md('step2', '## How Sure? Resample Weeks in Each Area\nThe public ratio in each area, with a 95% range as in notebook 01. Each area draws its own weeks, so the Monterey Bay range can differ by a hundredth from the one in notebook 01.'),
    sql('area_resample', '''
        WITH weekly_counts AS (
            SELECT
                dim_location.area,
                dim_location.area_order,
                DATEADD(DAY, 1 - dim_date.weekday_number, dim_date.date) AS week_start,
                COUNT_IF(dim_date.is_weekend) AS weekend_records,
                COUNT_IF(dim_date.is_midweek) AS midweek_records
            FROM fct_sighting
            JOIN dim_location ON dim_location.location_key = fct_sighting.location_key
            JOIN dim_date ON dim_date.date_key = fct_sighting.date_key
            JOIN dim_dataset ON dim_dataset.dataset_key = fct_sighting.dataset_key
            WHERE dim_dataset.kind = 'public'
            GROUP BY dim_location.area, dim_location.area_order, week_start
        ),

        numbered_weeks AS (
            SELECT
                area,
                area_order,
                ROW_NUMBER() OVER (PARTITION BY area ORDER BY week_start) AS week_number,
                COUNT(*) OVER (PARTITION BY area) AS total_weeks,
                weekend_records,
                midweek_records
            FROM weekly_counts
        ),

        replicates AS (
            SELECT SEQ4() AS replicate
            FROM TABLE(GENERATOR(ROWCOUNT => 2000))
        ),

        -- In each area, each replicate draws as many weeks as the area has,
        -- at random and with replacement.
        resample_draws AS (
            SELECT
                replicates.replicate,
                numbered_weeks.area,
                1 + MOD(
                    ABS(HASH(replicates.replicate, numbered_weeks.area, numbered_weeks.week_number, 20261016)),
                    numbered_weeks.total_weeks
                ) AS week_number
            FROM replicates
            CROSS JOIN numbered_weeks
        ),

        resampled_ratios AS (
            SELECT
                resample_draws.area,
                resample_draws.replicate,
                (SUM(numbered_weeks.weekend_records) / 2)
                / NULLIF(SUM(numbered_weeks.midweek_records) / 3, 0) AS weekend_ratio
            FROM resample_draws
            JOIN numbered_weeks
              ON numbered_weeks.area = resample_draws.area
             AND numbered_weeks.week_number = resample_draws.week_number
            GROUP BY resample_draws.area, resample_draws.replicate
        ),

        observed_ratios AS (
            SELECT
                area,
                ANY_VALUE(area_order) AS area_order,
                (SUM(weekend_records) / 2) / NULLIF(SUM(midweek_records) / 3, 0) AS weekend_ratio
            FROM numbered_weeks
            GROUP BY area
        )

        SELECT
            observed_ratios.area,
            ROUND(observed_ratios.weekend_ratio, 2) AS weekend_ratio,
            ROUND(PERCENTILE_CONT(0.025) WITHIN GROUP (ORDER BY resampled_ratios.weekend_ratio), 2)
                AS range_low,
            ROUND(PERCENTILE_CONT(0.975) WITHIN GROUP (ORDER BY resampled_ratios.weekend_ratio), 2)
                AS range_high
        FROM observed_ratios
        JOIN resampled_ratios ON resampled_ratios.area = observed_ratios.area
        GROUP BY observed_ratios.area, observed_ratios.area_order, observed_ratios.weekend_ratio
        ORDER BY observed_ratios.area_order
    '''),
    md('result', '''
        ## Result
        Public sightings rise at weekends in **4 of 5 areas**: a weekend day carries 1.44× the public sightings of a
        midweek day in Washington and British Columbia, 1.85× in northern California outside the bay, 1.52× in
        Monterey Bay and 1.83× in southern California. Oregon, with the fewest public records, shows none: a weekend
        day carries 0.87× the public sightings of a midweek day, and the 95% range (0.67 to 1.16) includes 1, no
        difference at all.
    '''),
    md('limits', '''
        ## Limits
        * Monterey has an unusually large whale-watching fleet; this comparison only sketches the effect elsewhere.
        * Puget Sound's main sighting network is not in the OBIS archive, so Washington's public records are
          undercounted.
    '''),
]))

for filename, cells in NOTEBOOKS:
    write(filename, cells)
marimo_nb.write_all(NOTEBOOKS)
marimo_nb.export_all(NOTEBOOKS)
