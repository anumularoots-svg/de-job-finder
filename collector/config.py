"""Settings for the collector. Edit this file to change what counts as a match."""
import os
import re

# Which job titles count as "Data Engineer" jobs.
TITLE_INCLUDE = re.compile(
    r"\bdata\s*engineer|\bdata\s+platform\s+engineer|\bbig\s+data\b.*\bengineer|"
    r"\betl\s+(developer|engineer)|\bdata\s+pipeline\s+engineer|\banalytics\s+engineer|"
    r"\bdata\s+warehouse\s+(engineer|developer)|\bdata\s+integration\s+engineer",
    re.I,
)
# Titles that match above but are not what we want.
TITLE_EXCLUDE = re.compile(
    r"\b(manager|director|head of|vp|vice president|intern|internship|principal architect|sales|recruiter)\b",
    re.I,
)

# Skills shown as chips and usable as filters.
SKILLS = [
    "Python", "SQL", "Spark", "PySpark", "Databricks", "Snowflake", "AWS", "Azure", "GCP",
    "Airflow", "dbt", "Kafka", "Scala", "Java", "Redshift", "BigQuery", "Glue", "EMR",
    "Hadoop", "Hive", "Terraform", "Docker", "Kubernetes", "ETL", "Informatica", "Talend",
    "SSIS", "ADF", "Synapse", "Delta Lake", "Iceberg", "Flink", "NoSQL", "MongoDB", "Postgres",
]

# How far back to keep jobs in the dashboard (the dashboard defaults to 24h).
MAX_AGE_DAYS = 14
# A job not seen by any source for this long is treated as closed.
STALE_AFTER_HOURS = 48

# Adzuna (free key from https://developer.adzuna.com). Set as GitHub secrets.
ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")
ADZUNA_PHRASES = ["data engineer", "etl developer", "big data engineer"]
ADZUNA_MAX_PAGES = 5          # 50 results per page
ADZUNA_MAX_DAYS_OLD = 3

USER_AGENT = "ZapkittJobFinder/1.0 (+https://zapkitt.com/dataenginer; personal job search)"
REQUEST_DELAY_SECONDS = 0.4    # polite pause between requests to the same host
TIMEOUT_SECONDS = 25

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}
