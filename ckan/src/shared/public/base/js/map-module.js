ckan.module("map-module", function ($, _) {
    return {
        options: { singleMode: true, enableBoundingBox: false },
        initialize: function () {
            this.EPSGTextElement = $("#field-epsg");
            this.EPSGCodeElement = $("#field-epsg_code");

            this.singleMode = this.options.singleMode;
            this.el.ready($.proxy(this.setupMap, this));

            this.setupElevationField();
        },

        setupMap: function () {
            var self = this;

            this.populateEPSG();
            this.prepopulateEPSG();

            var customIconPath = "base/vendor/leaflet/images/";
            L.Icon.Default.imagePath = this.options.site_url + customIconPath;

            this.map = L.map("map-container").setView([-31.9505, 115.8605], 3);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                maxZoom: 19,
                attribution: "© OpenStreetMap contributors",
            }).addTo(this.map);
            this.drawnItems = new L.FeatureGroup();
            this.markerItems = new L.FeatureGroup();

            this.resetMap();
            var selected = $("input[type=radio][name=location_choice]:checked").val();
            var allData = JSON.parse(this.el.attr("data-all-data"));
            let geoJSONStr = allData["location_data"];
            this.initializeFromGeoJSON(geoJSONStr);
            this.showMapAndInvalidate();

            // If bounding boxes are enabled via options, allow area selection
            if (this.options.enableBoundingBox && selected == "area") {
                this.initializeDrawControl();
                this.updateBoundsTable();
                this.updateBoundsFromTable(false);
                $("#bounding_box_coordinates").show();
            } else {
                // Default to point/marker mode
                this.initializeMarkerControl();
                this.updateMarkerTable();
                this.updateMarkerFromTable(false);
                $("#point_container").show();
            }

            $("html,body").scrollTop(0);

            $("input[type=radio][name=location_choice]").change(function () {
                self.resetMap();
                this.drawnItemsMap = {};
                self.updateMarkerTable();
                self.updateBoundsTable();
                var choice = $(this).val();
                if (choice == "area" && self.options.enableBoundingBox) {
                    self.showMapAndInvalidate();
                    self.initializeDrawControl();
                    $("#bounding_box_coordinates").show();
                } else {
                    self.showMapAndInvalidate();
                    self.initializeMarkerControl();
                    $("#point_container").show();
                }
            });
            $(".card-header").on("click", ".btn-link", function () {
                setTimeout(function () {
                    if (self.map) {
                        self.map.invalidateSize();
                    }
                }, 100);
            });
        },

        showMapAndInvalidate: function () {
            $("#map-container").show();
            $("#epsg_code_container").show();
            var self = this;
            setTimeout(function () {
                if (self.map) {
                    self.map.invalidateSize();
                }
            }, 100);
        },

        resetMap: function () {
            this.drawnItemsMap = {};
            this.drawnItems.clearLayers();
            this.markerItems.clearLayers();
            if (this.drawControl) {
                this.map.removeControl(this.drawControl);
                this.drawControl = null;
            }
            if (this.markerControl) {
                this.map.removeControl(this.markerControl);
                this.markerControl = null;
            }

            $("#point_container").hide();
            $("#bounding_box_coordinates").hide();
            $("#map-container").hide();
            $("#epsg_code_container").hide();
            this.map.off("click");
        },

        initializeDrawControl: function () {
            this.map.addLayer(this.drawnItems);
            if (!this.drawControl) {
                this.drawControl = new L.Control.Draw({
                    draw: {
                        polygon: false,
                        marker: false,
                        circlemarker: false,
                        circle: false,
                        polyline: false,
                        rectangle: true,
                    },
                    edit: {
                        featureGroup: this.drawnItems,
                        edit: true,
                        remove: true,
                    },
                });
            }
            this.map.addControl(this.drawControl);

            if (!this.rectangleDrawer) {
                this.rectangleDrawer = new L.Draw.Rectangle(
                    this.map,
                    this.drawControl.options.draw.rectangle
                );
            }
            // this.rectangleDrawer.enable();
            var self = this;
            this.map.off(L.Draw.Event.CREATED);
            this.map.on(L.Draw.Event.CREATED, function (event) {
                var layer = event.layer;
                var id = L.stamp(layer);
                if (self.singleMode) {
                    self.drawnItems.clearLayers();
                    self.drawnItemsMap = {};
                    document.getElementById("bounds-table-body").innerHTML = "";
                }
                self.drawnItems.addLayer(layer);
                if (layer instanceof L.Rectangle) {
                    var bounds = self.adjustBounds(layer.getBounds());
                    self.drawnItemsMap[id] = { type: "rectangle", bbox: bounds.toBBoxString() };
                    self.updateBoundsTable();
                }
            });

            this.map.off(L.Draw.Event.DELETED);
            this.map.on(L.Draw.Event.DELETED, function (event) {
                event.layers.eachLayer(function (layer) {
                    var id = L.stamp(layer);
                    delete self.drawnItemsMap[id];
                });
                self.updateBoundsTable();
            });

            this.map.off(L.Draw.Event.EDITED);
            this.map.on(L.Draw.Event.EDITED, function (event) {
                event.layers.eachLayer(function (layer) {
                    var id = L.stamp(layer);
                    if (layer instanceof L.Rectangle) {
                        var bounds = self.adjustBounds(layer.getBounds());
                        self.drawnItemsMap[id] = { type: "rectangle", bbox: bounds.toBBoxString() };
                    }
                });
                self.updateBoundsTable();
            });
        },

        initializeMarkerControl: function () {
            if (this.rectangleDrawer) {
                this.rectangleDrawer.disable();
            }
            this.map.addLayer(this.markerItems);
            if (!this.markerControl) {
                this.markerControl = new L.Control.Draw({
                    draw: {
                        polygon: false,
                        marker: true,
                        circlemarker: false,
                        circle: false,
                        polyline: false,
                        rectangle: false,
                    },
                    edit: {
                        featureGroup: this.markerItems,
                        edit: true,
                        remove: true,
                    },
                });
                this.map.addControl(this.markerControl);

                var self = this;

                this.map.off(L.Draw.Event.CREATED);
                this.map.on(L.Draw.Event.CREATED, function (event) {
                    var layer = event.layer;
                    if (event.layerType === "marker") {
                        // Check if singleMode is enabled
                        if (self.singleMode) {
                            self.markerItems.clearLayers();
                            self.drawnItemsMap = {};
                            document.getElementById("points-table-body").innerHTML = "";
                        }
                        var wrappedLatLng = layer.getLatLng().wrap();
                        self.markerItems.addLayer(layer);
                        var id = L.stamp(layer);
                        self.drawnItemsMap[id] = {
                            type: "marker",
                            lat: wrappedLatLng.lat,
                            lng: wrappedLatLng.lng,
                        };
                        self.updateMarkerTable();
                        layer.on("dragend", function (event) {
                            var marker = event.target;
                            var position = marker.getLatLng().wrap();
                            self.drawnItemsMap[id] = { type: "marker", lat: position.lat, lng: position.lng };
                            self.updateMarkerTable();
                        });
                    }
                });

                this.map.off(L.Draw.Event.DELETED);
                this.map.on(L.Draw.Event.DELETED, function (event) {
                    event.layers.eachLayer(function (layer) {
                        var id = L.stamp(layer);
                        if (self.drawnItemsMap[id]) {
                            delete self.drawnItemsMap[id];
                        }
                    });
                    self.updateMarkerTable();
                });
            }
        },

        updateMarkerTable: function () {
            var self = this;
            var tbody = document.getElementById("points-table-body");
            tbody.innerHTML = "";

            Object.keys(this.drawnItemsMap).forEach((id) => {
                var val = this.drawnItemsMap[id];
                if (val.type === "marker") {
                    var row = tbody.insertRow();
                    row.id = "marker-row-" + id;

                    var cellLng = row.insertCell();
                    var inputLng = document.createElement("input");
                    inputLng.type = "text";
                    inputLng.className = "form-control";
                    inputLng.value = val.lng;
                    cellLng.appendChild(inputLng);

                    var cellLat = row.insertCell();
                    var inputLat = document.createElement("input");
                    inputLat.type = "text";
                    inputLat.className = "form-control";
                    inputLat.value = val.lat;
                    cellLat.appendChild(inputLat);

                    inputLng.onchange = function () {
                        self.updateMarkerFromTable(id, parseFloat(this.value), "lng");
                    };

                    inputLat.onchange = function () {
                        self.updateMarkerFromTable(id, parseFloat(this.value), "lat");
                    };
                }
            });
            this.updateGeoJSON();
        },

        updateBoundsTable: function () {
            var tbody = document.getElementById("bounds-table-body");
            tbody.innerHTML = "";

            Object.keys(this.drawnItemsMap).forEach((id) => {
                var val = this.drawnItemsMap[id];
                if (val.type === "rectangle") {
                    var parts = val.bbox.split(",").map(function (coord) {
                        return parseFloat(coord);
                    });

                    var row = tbody.insertRow();
                    row.id = "bbox-row-" + id;

                    parts.forEach(function (coord, index) {
                        var cell = row.insertCell();
                        var input = document.createElement("input");
                        input.type = "text";
                        input.className = "form-control";
                        input.value = coord;
                        input.dataset.bboxId = id;
                        input.dataset.coordType = ["minLon", "minLat", "maxLon", "maxLat"][index];
                        input.onchange = (function (self) {
                            return function () {
                                var bboxId = this.dataset.bboxId;
                                var coordType = this.dataset.coordType;
                                self.updateBoundsFromTable(bboxId, coordType, this.value);
                            };
                        })(this);
                        cell.appendChild(input);
                    }, this);
                }
            }, this);

            this.updateGeoJSON();
        },

        updateMarkerFromTable: function (checkValidity = true) {
            this.markers = {};
            this.drawnItemsMap = {};
            this.markerItems.clearLayers();

            var rows = document.getElementById("points-table-body").rows;

            for (var i = 0; i < rows.length; i++) {
                var inputs = rows[i].getElementsByTagName("input");
                var lng = parseFloat(inputs[0].value);
                var lat = parseFloat(inputs[1].value);

                if (this.validatePointCoordinates(lat, lng)) {
                    var latLng = new L.LatLng(lat, lng);
                    var markerId = `marker-${i}`;
                    var marker = this.markers[markerId] || L.marker(latLng, { draggable: true });
                    this.markerItems.addLayer(marker);
                    marker.setLatLng(latLng);
                    var id = L.stamp(marker);
                    this.drawnItemsMap[id] = { type: "marker", lat: lat, lng: lng };
                    marker.on("dragend", (event) => {
                        var position = event.target.getLatLng().wrap();
                        this.drawnItemsMap[id] = { type: "marker", lat: position.lat, lng: position.lng };
                        this.updateMarkerTable();
                    });
                    if (!marker._hasDragendListener) {
                        marker._hasDragendListener = true;
                    }
                } else if (checkValidity) {
                    alert(
                        "Invalid point coordinates. Latitude must be between -90 and 90, Longitude between -180 and 180."
                    );
                    return;
                }
            }
            this.updateGeoJSON();
        },

        updateBoundsFromTable: function (checkValidity = true) {
            this.rectangles = {};
            this.drawnItemsMap = {};
            this.drawnItems.clearLayers();

            var rows = document.getElementById("bounds-table-body").rows;

            for (var i = 0; i < rows.length; i++) {
                var inputs = rows[i].getElementsByTagName("input");
                if (inputs.length === 4) {
                    var minLon = inputs[0].value,
                        minLat = inputs[1].value,
                        maxLon = inputs[2].value,
                        maxLat = inputs[3].value;
                    var bboxString = [minLon, minLat, maxLon, maxLat].join(",");

                    var bbox = bboxString.split(",").map(Number);
                    if (this.validateBoundingBoxCoordinates(bbox)) {
                        var bounds = L.latLngBounds([bbox[1], bbox[0]], [bbox[3], bbox[2]]);
                        var rectangleId = `rectangle-${i}`;

                        var rectangle = this.rectangles[rectangleId] || L.rectangle(bounds);
                        this.drawnItems.addLayer(rectangle);
                        rectangle.setBounds(bounds);
                        this.rectangles[rectangleId] = rectangle;
                        var id = L.stamp(rectangle);
                        this.drawnItemsMap[id] = { type: "rectangle", bbox: bboxString };
                    } else if (checkValidity) {
                        alert(
                            "Invalid bounding box coordinates. Please enter valid latitudes and longitudes."
                        );
                        return;
                    }
                }
            }
            this.updateGeoJSON();
        },

        updateGeoJSON: function () {
            let features = [];
            Object.values(this.drawnItemsMap).forEach((item) => {
                if (item.type === "marker") {
                    features.push({
                        type: "Feature",
                        geometry: {
                            type: "Point",
                            coordinates: [item.lng, item.lat],
                        },
                        properties: {},
                    });
                } else if (item.type === "rectangle") {
                    let bbox = item.bbox.split(",").map(Number);
                    features.push({
                        type: "Feature",
                        geometry: {
                            type: "Polygon",
                            coordinates: [
                                [
                                    [bbox[0], bbox[1]], // minLon, minLat
                                    [bbox[0], bbox[3]], // minLon, maxLat
                                    [bbox[2], bbox[3]], // maxLon, maxLat
                                    [bbox[2], bbox[1]], // maxLon, minLat
                                    [bbox[0], bbox[1]], // Closing loop to minLon, minLat
                                ],
                            ],
                        },
                        properties: {},
                    });
                }
            });
            let geoJSON = {
                type: "FeatureOrganisation",
                features: features,
            };
            document.getElementById("field-location_data").value = JSON.stringify(geoJSON, null, 2);
        },

        initializeFromGeoJSON: function (geoJSONStr) {
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

            geoJSONObject.features.forEach((feature, index) => {
                let id = `feature-${index}`;
                if (feature.geometry.type === "Point") {
                    let [lng, lat] = feature.geometry.coordinates;
                    this.drawnItemsMap[id] = { type: "marker", lat: lat, lng: lng };
                } else if (feature.geometry.type === "Polygon") {
                    let coordinates = feature.geometry.coordinates[0];
                    let minLon = coordinates.reduce((min, b) => Math.min(min, b[0]), coordinates[0][0]);
                    let maxLon = coordinates.reduce((max, b) => Math.max(max, b[0]), coordinates[0][0]);
                    let minLat = coordinates.reduce((min, b) => Math.min(min, b[1]), coordinates[0][1]);
                    let maxLat = coordinates.reduce((max, b) => Math.max(max, b[1]), coordinates[0][1]);
                    this.drawnItemsMap[id] = {
                        type: "rectangle",
                        bbox: `${minLon},${minLat},${maxLon},${maxLat}`,
                    };
                }
            });
        },

        validatePointCoordinates: function (lat, lng) {
            return !isNaN(lat) && !isNaN(lng) && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
        },

        validateBoundingBoxCoordinates: function (bboxString) {
            if (bboxString.length !== 4 || !bboxString.every((n) => !isNaN(n))) {
                return false;
            }
            var [minLng, minLat, maxLng, maxLat] = bboxString;
            var isValid =
                minLat >= -90 &&
                minLat <= 90 &&
                maxLat >= -90 &&
                maxLat <= 90 &&
                minLng >= -180 &&
                minLng <= 180 &&
                maxLng >= -180 &&
                maxLng <= 180 &&
                minLat < maxLat &&
                minLng < maxLng;
            return isValid;
        },

        adjustBounds: function (bounds) {
            let southwest = bounds.getSouthWest().wrap();
            let northeast = bounds.getNorthEast().wrap();

            let west = southwest.lng;
            let east = northeast.lng;
            let south = southwest.lat;
            let north = northeast.lat;

            if (east < west) {
                alert("Detected bounds that imply crossing the antimeridian");
                east += 360;
            }
            return L.latLngBounds([south, west], [north, east]);
        },

        populateEPSG: function () {
            var self = this;
            var nextPage = 0;
            var lastSearchTerm = null;

            self.EPSGCodeElement.select2({
                placeholder: "Search for an EPSG code",
                minimumInputLength: 0,
                delay: 250,
                cache: true,
                query: function (query) {
                    if (lastSearchTerm !== query.term) {
                        nextPage = 0;
                        lastSearchTerm = query.term;
                    }
                    var apiUrl = "/api/proxy/fetch_epsg";
                    var data = {
                        page: nextPage,
                        keywords: query.term,
                    };
                    $.ajax({
                        type: "GET",
                        url: apiUrl,
                        data: data,
                        dataType: "json",
                        success: function (data) {
                            var filteredItems = data.Results.filter(function (item) {
                                return item.Type === "geographic 2D" || item.Type === "compound";
                            }).map(function (item) {
                                return { id: item.Code, text: item.Code + " - " + item.Name };
                            });
                            nextPage = data.Page + 1;
                            query.callback({
                                results: filteredItems,
                                more: data.Page * data.PageSize < data.TotalResults,
                            });
                        },
                    });
                },
            }).on("change", function (e) {
                self.updateDependentFields();
            });
        },

        updateDependentFields: function () {
            var self = this;
            var selectedData = self.EPSGCodeElement.select2("data");
            self.EPSGTextElement.val(selectedData.text);
        },

        prepopulateEPSG: function () {
            var existingId = this.EPSGCodeElement.val();
            var existingText = this.EPSGTextElement.val();
            if (!existingId || existingId.trim() === "") {
                // Set default values
                this.EPSGCodeElement.val("4326");
                this.EPSGTextElement.val("4326 - WGS 84");
                existingId = "4326";
                existingText = "4326 - WGS 84";
            }
            var dataForSelect2 = { id: existingId, text: existingText };
            this.EPSGCodeElement.select2("data", dataForSelect2, true);
        },

        setupElevationField: function () {
            document.getElementById("field-elevation").addEventListener("input", function (event) {
                const inputField = event.target;
                const value = inputField.value;
                const validValue = value.replace(/[^0-9.]/g, "");
                const parts = validValue.split(".");
                if (parts.length > 2) {
                    inputField.value = parts[0] + "." + parts.slice(1).join("");
                } else {
                    inputField.value = validValue;
                }
                if (parseFloat(inputField.value) < 0) {
                    inputField.value = "";
                }
            });
        },
    };
});
