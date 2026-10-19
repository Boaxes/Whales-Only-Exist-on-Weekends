{# Use the schema a model asks for (RAW, MARTS) as is, instead of dbt's default <target>_<custom> name. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim | upper }}
{%- endmacro %}
