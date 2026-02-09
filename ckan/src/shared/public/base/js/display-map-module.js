ckan.module('display-map-module', function ($, _) {
    return {
        initialize: function () {
            this.el.ready($.proxy(this.setupMap, this));
            this.decimalPrecision = 5;
        },

        setupMap: function () {
            var allData = JSON.parse(this.el.attr('data-all-data'));
            var locationChoice = allData['location_choice'];
            if (locationChoice != null && locationChoice != "noLocation") {
                $('#map-container').show();
                $('#epsg-info').show();

                if (locationChoice == "point") {
                    this.initializeMapWithPoints(allData['location_data']);
                } else if (locationChoice == "area") {
                    this.initializeMapWithBoundingBoxes(allData['location_data']);
                }
            } else {
                $('#location-info').text('Location not specified.');
            }
        },
        initializeMapWithPoints: function (geoJSONStr) {
            var self = this;
            var customIconPath = 'base/vendor/leaflet/images/';
            L.Icon.Default.imagePath = this.options.site_url + customIconPath;

            var geoJSONObject;

            if (typeof geoJSONStr === "string") {
                try {
                    geoJSONObject = JSON.parse(geoJSONStr);
                } catch (e) {
                    console.error("Error parsing GeoJSON string:", e);
                    return;
                }
            } else if (typeof geoJSONStr === "object") {
                geoJSONObject = geoJSONStr;
            } else {
                console.error("Invalid GeoJSON data type:", typeof geoJSONStr);
                return;
            }

            var pointFeatures = geoJSONObject.features.filter(function (feature) {
                return feature.geometry.type === 'Point';
            });

            var map = L.map('map-container').setView([0, 0], 2); 
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
                maxZoom: 19,
            }).addTo(map);

            if (pointFeatures.length === 0) {
                $('#location-info').html('No point data available').attr('style', 'padding-top: 10px; font-size: small;');
                return;
            }

            var markers = [];
            var orderText = 'Point: [Longitude, Latitude]';
            var pointsInfo = pointFeatures.map(function (feature) {
                var coords = feature.geometry.coordinates;
                var marker = L.marker([coords[1], coords[0]]).addTo(map);
                markers.push(marker);
                return `[${parseFloat(coords[0]).toFixed(self.decimalPrecision)}, ${parseFloat(coords[1]).toFixed(self.decimalPrecision)}]`;
            }).join(', ');

            if (markers.length > 0) {
                var group = L.featureGroup(markers);
                map.fitBounds(group.getBounds(), { padding: [50, 50] });
            }
            $('#location-info').html(orderText + '<br>' + pointsInfo).attr('style', 'padding-top: 10px; font-size: small;');
        },



        initializeMapWithBoundingBoxes: function (geoJSONStr) {
            var self = this;
            if (typeof geoJSONStr === "string") {
                try {
                    geoJSONObject = JSON.parse(geoJSONStr);
                } catch (e) {
                    console.error("Error parsing GeoJSON string:", e);
                    return;
                }
            } else if (typeof geoJSONStr === "object") {
                geoJSONObject = geoJSONStr;
            } else {
                console.error("Invalid GeoJSON data type:", typeof geoJSONStr);
                return;
            }

            var map = L.map('map-container').setView([0, 0], 1);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
                maxZoom: 19,
            }).addTo(map);

            var orderText = 'BBox: [Min Longitude, Min Latitude, Max Longitude, Max Latitude]';
            var bboxesInfo = geoJSONObject.features.map(function (feature, idx) {
                var coordinates = feature.geometry.coordinates[0];
                var bounds = [
                    [coordinates[0][1], coordinates[0][0]], // Bottom left
                    [coordinates[2][1], coordinates[2][0]]  // Top right
                ];
                L.rectangle(bounds).addTo(map);

                return `BBox ${idx + 1}: [${coordinates[0][0].toFixed(self.decimalPrecision)}, ${coordinates[0][1].toFixed(self.decimalPrecision)}, ${coordinates[2][0].toFixed(self.decimalPrecision)}, ${coordinates[2][1].toFixed(self.decimalPrecision)}]`;
            }).join('<br>');

            if (geoJSONObject.features.length > 0) {
                var group = L.featureGroup();
                geoJSONObject.features.forEach(function (feature) {
                    if (feature.geometry.type === 'Polygon') {
                        var bounds = feature.geometry.coordinates[0].map(function (coord) {
                            return [coord[1], coord[0]]; // Leaflet uses [lat, lng]
                        });
                        var rectangle = L.rectangle(bounds).addTo(map);
                        group.addLayer(rectangle);
                    }
                });
                map.fitBounds(group.getBounds(),{ padding: [50, 50] });
            } else {
                console.error("No features found in GeoJSON.");
            }

            $('#location-info').html(orderText + '<br>' + bboxesInfo).attr('style', 'padding-top: 10px; font-size: small;');
        },


    };
});
