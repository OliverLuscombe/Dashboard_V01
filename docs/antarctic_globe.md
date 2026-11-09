# Antarctic CSV globe

Map Explorer uses uploaded CSV observations on a south-polar globe with a coastline basemap. Overview and the old pixel-grid renderer are no longer part of the application. The globe places observations using the mapped Latitude and Longitude columns and sends all selected CSV observations to one batched Deck.gl WebGL layer.

## Importing and grouping snapshots

Enter a whole-number Year (1–9999) and Month (1–12) before each CSV import. The date is saved as dataset metadata and is not added to or read from CSV columns. Select a dataset in Data, map Latitude, Longitude, and at least one supported numeric measurement, then apply it as a globe layer.

Map Explorer groups mapped CSVs by Year and Month. Choose one group to display its layers; enable multiple CSVs in that group at once. Enabling or removing one layer does not change active layers in other date groups. Older mapped datasets without date metadata appear under **Undated**. CSVs that have no valid geographic mapping are not offered as globe layers.

## Measurements, summaries, and inspection

The measurement selector contains only fields mapped by CSVs in the selected date group. Valid coordinates must be finite values within latitude −90–90 and longitude −180–180. Rows with missing or invalid coordinates or selected measurements are omitted from the point payload.

Sea-ice concentration readings must be in the range 0–100. If all valid readings in a CSV are at most 1, that CSV's values are treated as fractions and converted to percent. The globe's concentration legend spans 0–100%. Other supported measurements (sea-surface temperature, wind speed, and air temperature) retain their observed units and range; values are normalized only for the shared colour scale. The displayed mean is computed from valid readings in the active CSV layers.

Click an observation to inspect its CSV name, mapped column, value, latitude, and longitude. The point elevation is a visual offset only. The globe does not represent ice thickness, Antarctic terrain, sea-ice extent, or a trained model.

## Comparing snapshots

The Compare workspace provides two independent selectors populated from the available mapped CSV Year/Month groups. Select any pair, including two months within the same year. Multiple mapped CSV files for a selected month are pooled; active Map Explorer toggles do not limit comparison. Choose a measurement available in both snapshots to see each snapshot's mean, valid observation count, number of mapped files, and the difference (second mean minus first mean). Means use valid numeric readings with valid geographic coordinates, and fractional concentration values are converted to percent per file.

Below the summary cards, the difference globe bins observations into 0.5° latitude × 1° longitude cells. It compares the mean in each cell between the selected snapshots and displays only cells with valid readings in both. Blue indicates a decrease, red an increase, and neutral grey a difference near zero; the colour range is symmetric around zero. Clicking a cell shows both means, the difference, and sample counts. The binning is for visualization, not an area-weighted scientific comparison; unmatched cells are omitted and no spatial interpolation is performed.

The coastline basemap requires network access. The upload workspace is shared and has no authentication; do not upload confidential or personal data.
