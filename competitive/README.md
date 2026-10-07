# Competitive set

3,881 garages in 302 cities and 7 countries, with operator, location, capacity and
published price. This is the dataset of the former **parkingsimulator** project
(github.com/friedrichdemmer-ctrl/parkingsimulator, last commit `d7ac533`, 2026-10-05),
brought in here so that project can be retired. Everything it held is now in this
repository: the data here, the maps in the site ("Local maps"), and the simulator
code and results under `archive/parkingsimulator/`.

`european_parking.csv` -- one row per garage. Columns: `country, city, id` (unique within a
city only), `name, operator, lat, lon, capacity, hourly_rate` (first-hour or flat hourly rate),
`daily_cap` (24-hour price), `has_ev` (True where charging was confirmed; blank is unconfirmed),
`address, source_url, currency`.

Scope: every city where Q-Park operates, with Q-Park plus the real competing operators found there.
Names, addresses, capacities and prices are taken from each operator's own site or live pricing
API; coordinates come from the pages' embedded data or OpenStreetMap. **A blank means the operator
does not publish a usable value; nothing is estimated.** Indigo, Effia and some others publish no
capacity (644 garages have none), and 964 have no hourly rate (free first hour, stepped tariffs,
or simply unpublished). Coverage is a full list for small cities but a sample for the largest
(Paris Indigo, Copenhagen APCOA).

`notes/<cc>_progress.csv` -- the research log for each country, one row per city: what was found,
which sources, which operators were confirmed absent, and which rows were excluded and why. Read
the row for a city before trusting its numbers.

`links.csv` -- which of these garages is also one of ours (a garage we measure occupancy for),
matched by location, name and capacity; see `competitive_links.py`. Garages without a link have a
price but no occupancy. A `dist_m` of -1 marks a row matched on name alone, within the same city,
because our feed publishes no coordinates for that garage (Hamburg, Dresden, Bonn, Lübeck, Nürnberg,
the Dutch national register and others); those rows need a much closer name agreement to be accepted.
A missing link is not harmless: the city briefing then counts the same garage twice, once from the
price list and once from the occupancy feed (Bonn read as 20 garages and 8,721 spaces before the
name pass linked its seven BCP garages).

The site reads this through `competitive.py`. Regenerate `links.csv` after either side gains garages.
