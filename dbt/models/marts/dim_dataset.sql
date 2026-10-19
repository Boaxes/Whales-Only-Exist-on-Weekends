-- One row per OBIS dataset. OBIS names a dataset only by a UUID and a title; nothing says who recorded it.
-- The dataset_kind seed sorts all 117 by hand into public, survey (ship or aircraft), hydrophone and other.

SELECT
    HASH(obis_dataset.dataset_id) AS dataset_key,
    obis_dataset.dataset_id,
    obis_dataset.title,
    dataset_kind.kind
FROM {{ source('raw', 'obis_dataset') }} AS obis_dataset
LEFT JOIN {{ ref('dataset_kind') }} AS dataset_kind ON dataset_kind.dataset_id = obis_dataset.dataset_id
