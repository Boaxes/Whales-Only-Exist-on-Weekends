{# True when a point is strictly inside the Monterey Bay box set in dbt_project.yml. #}
{% macro in_bay(lat, lon) -%}
    ({{ lat }} > {{ var('bay_lat')[0] }} AND {{ lat }} < {{ var('bay_lat')[1] }}
     AND {{ lon }} > {{ var('bay_lon')[0] }} AND {{ lon }} < {{ var('bay_lon')[1] }})
{%- endmacro %}
