# 1675 Summit Point Ct, Colorado Springs, CO 80919: GIS pull for the deck permit site plan

APN 7311205063 | zoning PDZ HS (from the parcel layer). Pulled 2026-10-22. All files are in this folder. Raw server responses are in `downloads/`.

## Sources (City of Colorado Springs ArcGIS Server 11.3)
- Geocode: https://gis.coloradosprings.gov/arcgis/rest/services/AddressLocators/E911_Sites_Locator/GeocodeServer (score 100, PointAddress). The `LandRecords/MapServer/0` address point has the same location.
- Parcel: https://gis.coloradosprings.gov/arcgis/rest/services/GeneralUse/LandRecords/MapServer/4 (PARCEL=7311205063, Shape_Area 16,961 sf)
- Building footprint: https://gis.coloradosprings.gov/arcgis/rest/services/GeneralUse/BuildingsImpSurfaces/MapServer/0 (OBJECTID 147225). Stories, height and elevation come from https://gis.coloradosprings.gov/arcgis/rest/services/ZoningPortal/Buildings/MapServer/0
- Streets: https://gis.coloradosprings.gov/arcgis/rest/services/GeneralUse/Transportation/MapServer/8
- Aerials: https://gis.coloradosprings.gov/arcgis/rest/services/Basemaps/AerialsBasemap/MapServer/export (the current one; the service does not publish its year). Also https://gis.coloradosprings.gov/arcgis/rest/services/Basemaps/HistoricalAerials/MapServer (layer 0 = 2018, layer 5 = 2022).
- maps.elpasoco.com could not be reached from this environment (the proxy refused it). Microsoft footprints were not needed.

## Files
| File | Content |
|---|---|
| parcel.json | Parcel polygon, GeoJSON, EPSG:4326 |
| footprint.json | House footprint, GeoJSON, EPSG:4326 |
| aerial.jpg / aerial_2018.jpg / aerial_2022.jpg | 1000x1000 px, 200x200 ft (61 m), 0.2 ft/px. Bbox is in aerial_bbox.json |
| plan_frame.json | Parcel, footprint and decks in the local plan frame (ft), plus the distances to the lot lines |
| plan_overlay_current.png / plan_overlay_2018.png | Aerial resampled into the plan frame, with a 10 ft grid. Parcel in yellow, footprint in red, estimated decks in green. +x right, +y down (a true view from above) |

## Key numbers
- Address point: lat 38.938778, lon -104.862917 (verified)
- Rear of the house: the long SW face, 68.1 ft along the footprint line. Its outward normal bears **210.8 deg true** (the wall runs at 120.8 deg).
- Street: **Summit Point Ct** runs along the north (front) lot line only. The other lot lines are neighbours: west side 1685 Summit Point Ct, east side 1665 Summit Point Ct, rear (south) 1856 Oak Hills Dr.
- Distances from the house footprint to the lot lines: front 23.5 ft, west 7.8 ft, east 7.6 ft, rear 62.8 ft.
- Existing decks, in plan-frame ft with y measured from the mapped dripline:
  - Small deck, W end: x 8 to 25, y 0 to 8. About 12 ft to the west line, 72 ft to the rear line.
  - Large L deck, rear leg: x 48 to 79, y 0 to 8. Return leg on the SE side: x 68 to 79, y -27 to 0. About 7.8 ft to the east line, 51 ft to the rear line.

## Verified vs estimated
- **Verified** (straight from the GIS attributes and geometry): the geocode, the parcel polygon and area, the footprint polygon, the street name and the neighbouring parcels.
- **Derived**: the rear-wall azimuth and the plan-frame coordinates. These are exact transforms of the GIS geometry through EPSG:2232, with grid convergence (about 0.4 deg) removed.
- **Inferred**:
  - The footprint seems to follow the roof/dripline, so it probably includes the eaves. The metadata does not say. The plan-frame origin is on that line, so the actual wall face is probably about 1 to 2 ft toward the house (y < 0).
  - The front lot line lies on the Summit Point Ct centerline, within about 1 ft. Check this against the plat (the street may be a private tract or easement).
- **Estimated**: the deck outlines. They were digitized by eye from orthos that are not true orthos, at about +/-1.5 to 3 ft. What I measured does not fully match the descriptions I was given:
  - Large deck rear leg: about 31 ft visible, against about 37 ft stated.
  - Small deck: about 17 x 8 ft or more, against about 10x10 ft stated.

  Measure both on site.
- **Frame handedness**: with +x to the right as seen from the yard and +y into the yard, the frame is mirrored relative to a map. Plot it with +y down (house at the top), or flip x, to get a true plan view.
