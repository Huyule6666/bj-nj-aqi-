require(["dojo/_base/window",
    "esri/map",
    "esri/layers/ArcGISDynamicMapServiceLayer",
    "esri/geometry/Extent",
    "esri/dijit/Scalebar",
    "dojo/parser",
    "dojo/request",
    "dojo/on",
    "dojo/_base/config",
    "controls/basemaptoggle",
    "controls/navigator",
    "controls/sidepanel",
    "controls/accordion",
    "controls/factor",
    "dijit/layout/BorderContainer",
    "dijit/layout/ContentPane",
    "dojo/domReady!"],
    function (win, Map, ArcGISDynamicMapServiceLayer, Extent, Scalebar, parser, request, on, config, BasemapToggle, Navigator, SidePanel, Accordion, Factor) {

        parser.parse();
        config.busy = document.querySelector("#busyIndicator");

        var extent = new Extent({ "xmin": config.xmin, "ymin": config.ymin, "xmax": config.xmax, "ymax": config.ymax });
        var map = new Map("map", {
            extent: extent,
            showAttribution: false,
            slider: false,
            logo: false
        });
        var scalebar = new Scalebar({
            map: map,
            scalebarUnit: "metric"
        });
        config.map = map;

        var basemaptoggle = new BasemapToggle();
        basemaptoggle.placeAt(document.querySelector("#basemaptoggle"));

        var borderlayer = new ArcGISDynamicMapServiceLayer("http://218.94.78.75:6080/ArcGIS/rest/services/JSJJ/MapServer/");
        borderlayer.setOpacity(0.5);
        map.addLayer(borderlayer);

        var navigator = new Navigator({ map: map });
        navigator.placeAt(document.querySelector("#navigator"));

        request.get("services/LoadConfiguration.ashx").then(
            function (result) {
                result = decrypt(result);
                var myconfig = eval("(" + result + ")").menu;

                request.get("services/查询区域信息.ashx").then(
                    function (areajson) {
                        areajson = decrypt(areajson);
                        config.area = JSON.parse(areajson).data;

                        var sidepanel_container = document.querySelector("#sidepanel");
                        var sidepanel = new SidePanel();
                        sidepanel.placeAt(sidepanel_container);
                        sidepanel.init(myconfig.menuitem[0].menuitem[0]);

                        on(map, "zoom-end", function (evt) {
                            sidepanel.setLevel(evt.level);
                        });

                        var accordion_container = document.querySelector("#accordion");
                        var accordion = new Accordion({ menu: myconfig.menuitem,blocked:"1-3" });
                        accordion.placeAt(accordion_container);
                        accordion.setMenu(myconfig.menuitem[0]);

                        var factor_container = document.querySelector("#factor");
                        var factor = new Factor();
                        factor.placeAt(factor_container);
                        on(factor, "selected", function (e) {
                            for (var i = map.graphicsLayerIds.length - 1; i >= 0; i--) {
                                var layer = map.getLayer(map.graphicsLayerIds[i]);
                                layer.setFactor(e.factor);
                            }
                        });
                        var datetime = document.querySelector("#datetime");
                        var legend = document.querySelector("#legend");

                        var sidebutton = document.querySelector("#sidebutton");
                        var sidebutton_right = 250;
                        on(sidebutton, "click", function () {
                            if (sidepanel_container.style.display == "none") {
                                sidepanel_container.style.display = "block";
                                sidepanel_container.style.backgroundImage = "url(images/按钮背景1.png)";
                                sidebutton.style.right = sidebutton_right + "px";
                                if (factor_container.style.display == "block" || factor_container.style.display == "") {
                                    factor_container.style.right = (sidebutton_right + 50) + "px";
                                    datetime.style.right = (sidebutton_right + 160) + "px";
                                }
                                else
                                    datetime.style.right = (sidebutton_right + 50) + "px";
                            }
                            else {
                                sidepanel_container.style.display = "none";
                                sidebutton.style.backgroundImage = "url(images/按钮背景2.png)";
                                sidebutton.style.right = "0";
                                if (factor_container.style.display == "block" || factor_container.style.display == "") {
                                    factor_container.style.right = "50px";
                                    datetime.style.right = "160px";
                                }
                                else
                                    datetime.style.right = "50px";
                            }
                        });

                        on(accordion, "selected", function (e) {
                            if (e.item.enabled == "true")
                                goModule(e.item)
                            else if (e.item.enabled == "false")
                                window.open(e.item.href, "_blank");
                        });

                        function goModule(item) {
                            map.infoWindow.hide();
                            for (var i = map.graphicsLayerIds.length - 1; i >= 0; i--) {
                                var layer = map.getLayer(map.graphicsLayerIds[i]);
                                map.removeLayer(layer);
                            }
                            if (item.id == "1-1")
                                factor_container.style.display = "block";
                            else
                                factor_container.style.display = "none";
                            if (item.id == "1-1" || item.id == "1-2" || item.id == "1-3-1") {
                                legend.style.display = "block";
                                legend.style.backgroundImage = "url(images/空气图例.png)";
                            }
                            //else if (item.id == "2-1-1" || item.id == "2-2") {
                            //    legend.style.display = "block";
                            //    legend.style.backgroundImage = "url(images/水质图例.png)";
                            //}
							else if (item.id == "2-2") {
                                legend.style.display = "block";
                                legend.style.backgroundImage = "url(images/水质图例.png)";
                            }
                            else
                                legend.style.display = "none";
                            if (item.id == "2-2") {
                                var extent2 = new Extent({ "xmin": 119.018, "ymin": 30.786, "xmax": 121.463, "ymax": 32.168 });
                                map.setExtent(extent2);
                            }
                            else
                                map.setExtent(extent);
                            if (item.id == "2-2" || item.id == "2-3") {
                                sidepanel_container.style.display = "none";
                                sidebutton.style.display = "none";
                            }
                            else {
                                sidepanel_container.style.display = "block";
                                sidebutton.style.display = "block";
                                sidebutton_right = 0;
                            }
                            if (item.id == "2-3" || item.id == "2-4")
                                datetime.style.display = "none";
                            else
                                datetime.style.display = "block";

                            if (item.id == "1-1") {
                                sidepanel_container.style.width = "250px";
                                sidebutton.style.right = "250px";
                                datetime.style.right = "420px";
                                sidebutton_right = 250;
                            }
                            else if (item.id == "1-2" || item.id == "1-3-1") {
                                sidepanel_container.style.width = "460px";
                                sidebutton.style.right = "460px";
                                sidebutton_right = 460;
                                datetime.style.right = "510px";
                            }
                            else if (item.id == "2-1-1") {
                                sidepanel_container.style.width = "250px";
                                sidebutton.style.right = "250px";
                                datetime.style.right = "300px";
                                sidebutton_right = 300;
                            }
                            else if (item.id == "2-2") {
                                datetime.style.right = "10px";
                            }
                            else if (item.id == "2-4") {
                                sidepanel_container.style.width = "350px";
                                sidebutton.style.right = "350px";
                                datetime.style.right = "400px";
                                sidebutton_right = 350;
                            }
                            sidepanel.init(item);
                        }
                    });
            });
    });