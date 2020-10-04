         // TODO: videos
         // TODO: end-to-end automation
         // TODO: elevation inset with profile, current slide location
         // TODO: UI to filter out videos, pic categories, etc (doesnt work by simply hiding the <a>'s - maybe i can move them to/from a different div somehow?)
         // TODO: better design - map not an overlay, or hideable, or something
         // TODO: open gallery on page load
         // TODO: interpolate location from timestamp if necessary
         // TODO load tracks from geoJSON files from server
         // TODO move waypoints, annotations to geoJSON files, load from server

         // DONE: factor out all trip-specific data
         // DONE: generate the main data
         // DONE: map inset with tracks, waypoints, and current slide location
         // DONE: better icons
         // DONE: image-specific anchor links

         $(document).ready(function() {
             $("#lightgallery").lightGallery({
                 thumbnail: true,
                 animateThumb: true,
                 showThumbByDefault: true,
                 videojs: true
             });
         });

         var map = L.map('mapid', {
             keyboard: false,
         }).setView(mapCenter, 12);

         L.tileLayer('https://api.mapbox.com/styles/v1/{id}/tiles/{z}/{x}/{y}?access_token={accessToken}', {
             maxZoom: 18,
             id: 'mapbox/satellite-v9',
             accessToken: mapboxAccessToken,
         }).addTo(map);


         c = annotations["circles"];
         for (var n in c) {
             var circle = L.circle(c[n]["center"], c[n]["options"]).addTo(map)
             circle.bindPopup(c[n]["caption"])
         }

         for (var title in waypoints) {
             icon = waypoints[title][1]
             //console.log(icon)
             var marker = L.marker(waypoints[title][0], {icon: icon}).addTo(map);
             marker.bindPopup(title);
         }

         var start = waypoints[startWaypointName]
         var currentLocMarker = L.marker(start[0], {icon: currentIcon}).addTo(map);
         currentLocMarker.bindPopup("current photo");

         for(n=0; n<tracks.length; n++) {
             L.geoJson(tracks[n], {style: {color: tab10[n], weight: 3, opacity: 1}}).addTo(map);
         }

         function updateMapInset(lat, lon) {
             currentLocMarker.setLatLng([lat, lon]);

             // center map on this point, but only if it's not already close to the center
             bounds = map.getBounds();
             // center = map.getCenter();
             xnorm = (lon - bounds._northEast["lng"])/(bounds._southWest["lng"] - bounds._northEast["lng"])
             ynorm = (lat - bounds._southWest["lat"])/(bounds._northEast["lat"] - bounds._southWest["lat"])
             if (xnorm < .25 || xnorm > .75 || ynorm < .25 || ynorm > .75) {
                 map.flyTo([lat, lon], map.getZoom());
             }

         }

         // attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors, <a href="https://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
         // Campground by Vicons Design from the Noun Project
         // Spork by Matt Garbarino from the Noun Project

         $("#lightgallery").on('onBeforeSlide.lg', function(event, prevIndex, index){
             //$('.lg-outer').css('background-color', colours[index])
             console.log(event, prevIndex, index)
             slide=$("#slide" + index)[0]
             console.log(slide)
             lat = parseFloat(slide.attributes["data-lat"].value)
             lon = parseFloat(slide.attributes["data-lon"].value)
             console.log(slide, lat, lon)
             updateMapInset(lat, lon)
         });

         $("#lightgallery").on('onAfterOpen.lg',function(event, index, fromTouch, fromThumb){
             console.log("onAfterOpen")
         });
