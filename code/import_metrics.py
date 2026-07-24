#!/usr/bin/python3

import helpers_pl as helpers
import sql_stuff
import sqlite2_polars

for record in helpers.get_metric_desc_from_manpage():
    sql_stuff.add_metric(record[0], record[1])

# Rebuild the cached copy once at the end - otherwise the bulk import stays
# invisible to the running processes.
sqlite2_polars.invalidate_table_cache("metric")