-- One row per taxon a record was identified to. A subspecies counts as its species (OBIS gives the species
-- alongside the subspecies name); a record identified only to genus, family or higher keeps that name.
-- That turns 57 recorded names into 48 taxa. Common names come from the species_names seed, because the
-- records' own vernacular names disagree with each other.

WITH recorded_taxa AS (
    SELECT DISTINCT
        COALESCE(obis_occurrence.interpreted:species::STRING, obis_occurrence.interpreted:scientificName::STRING) AS taxon
    FROM {{ source('raw', 'obis_occurrence') }} AS obis_occurrence
    WHERE NOT obis_occurrence.absence
      AND NOT obis_occurrence.dropped
)

SELECT
    HASH(recorded_taxa.taxon) AS species_key,
    recorded_taxa.taxon AS scientific_name,
    species_names.common_name
FROM recorded_taxa
LEFT JOIN {{ ref('species_names') }} AS species_names ON species_names.taxon = recorded_taxa.taxon
