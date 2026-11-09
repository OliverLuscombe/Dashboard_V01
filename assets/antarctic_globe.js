(() => {
  const activeMaps = new Map();
  const observationAltitudeMeters = 18000;

  const colorAt = (value) => {
    const stops = [
      [0, [23, 50, 77]],
      [30, [40, 120, 165]],
      [58, [102, 184, 165]],
      [78, [242, 223, 119]],
      [100, [217, 75, 55]],
    ];
    const upper = stops.findIndex(([limit]) => value <= limit);
    if (upper <= 0) return [...stops[0][1], 230];
    const [lowValue, lowColor] = stops[upper - 1];
    const [highValue, highColor] = stops[upper];
    const amount = (value - lowValue) / (highValue - lowValue);
    return [
      ...lowColor.map((channel, index) =>
        Math.round(channel + (highColor[index] - channel) * amount),
      ),
      230,
    ];
  };

  const differenceColorAt = (value, maxAbs) => {
    const neutral = [242, 244, 246];
    const negative = [38, 105, 154];
    const positive = [190, 56, 48];
    const amount =
      maxAbs > 0 ? Math.min(1, Math.abs(value) / maxAbs) : 0;
    const endpoint = value < 0 ? negative : positive;
    return [
      ...neutral.map((channel, index) =>
        Math.round(channel + (endpoint[index] - channel) * amount),
      ),
      235,
    ];
  };

  const showError = (element, message) => {
    let notice = element.parentElement.querySelector(
      ".antarctic-globe-runtime-error",
    );
    if (!notice) {
      notice = document.createElement("p");
      notice.className =
        "antarctic-globe-runtime-error border-t border-red-200 bg-red-50 p-3 text-xs text-red-700";
      notice.setAttribute("role", "alert");
      element.insertAdjacentElement("afterend", notice);
    }
    notice.textContent = message;
  };

  const clearError = (element) => {
    element.parentElement
      .querySelector(".antarctic-globe-runtime-error")
      ?.remove();
  };

  const setPoints = async (entry, source) => {
    if (!source || source === entry.source) return;
    entry.source = source;
    try {
      const response = await fetch(source, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Point data request failed (${response.status}).`);
      }
      const payload = await response.json();
      if (!Array.isArray(payload.points)) {
        throw new Error("The generated point data is invalid.");
      }
      if (entry.source !== source) return;
      entry.points = payload.points;
      entry.colorMode = payload.color_mode || "measurement";
      entry.maxAbs = Number(payload.max_abs) || 0;
      if (entry.overlay) {
        entry.overlay.setProps({ layers: [entry.layer(payload.points)] });
      }
      clearError(entry.element);
    } catch (error) {
      console.error("Could not load Antarctic globe observations.", error);
      showError(entry.element, "Globe observations could not be loaded. Refresh the globe to retry.");
    }
  };

  const mount = (element) => {
    const source = element.getAttribute("data-globe-source");
    let entry = activeMaps.get(element);
    if (entry) {
      void setPoints(entry, source);
      return;
    }
    if (!source) return;
    if (!window.maplibregl || !window.deck?.ScatterplotLayer || !window.deck?.MapboxOverlay) {
      showError(element, "The globe libraries did not load. Check network access and refresh.");
      return;
    }

    const showObservation = (info) => {
      if (!info.object) return;
      const [longitude, latitude, , value, dataset, column, units] =
        info.object;
      const content = document.createElement("div");
      content.className = "text-xs leading-relaxed";
      const title = document.createElement("strong");
      const details = document.createElement("p");
      details.className = "mt-1";
      if (entry.colorMode === "difference") {
        const [
          ,
          ,
          difference,
          meanA,
          meanB,
          countA,
          countB,
          units,
        ] = info.object;
        title.textContent = "Spatial-cell comparison";
        const periods =
          element.getAttribute("data-globe-periods") || "Selected snapshots";
        details.textContent =
          `${periods}: ${Number(meanB).toLocaleString(undefined, {
            maximumFractionDigits: 4,
          })} − ${Number(meanA).toLocaleString(undefined, {
            maximumFractionDigits: 4,
          })} = ${Number(difference).toLocaleString(undefined, {
            maximumFractionDigits: 4,
          })} ${units}. ${countA} and ${countB} observations in the matched cell. Cell centre ${Number(
            latitude,
          ).toFixed(2)}°, ${Number(longitude).toFixed(2)}°.`;
      } else {
        title.textContent = dataset;
        const snapshot =
          element.getAttribute("data-globe-snapshot") || "Undated";
        const measurement =
          element.getAttribute("data-globe-measurement") || column;
        details.textContent =
          `${measurement} (${column}): ${Number(value).toLocaleString(undefined, {
          maximumFractionDigits: 4,
        })} ${units} · ${Number(latitude).toFixed(3)}°, ${Number(longitude).toFixed(3)}° · ${snapshot}`;
      }
      content.append(title, details);
      new window.maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
        .setLngLat([longitude, latitude])
        .setDOMContent(content)
        .addTo(map);
    };

    const layer = (points) =>
      new window.deck.ScatterplotLayer({
        id: "antarctic-sea-ice-observations",
        data: points,
        getPosition: (point) => [
          point[0],
          point[1],
          observationAltitudeMeters,
        ],
        getFillColor: (point) =>
          entry.colorMode === "difference"
            ? differenceColorAt(point[2], entry.maxAbs)
            : colorAt(point[2]),
        getRadius: entry.colorMode === "difference" ? 42000 : 18000,
        radiusUnits: "meters",
        radiusMinPixels: 2.75,
        radiusMaxPixels: 10,
        opacity: 0.96,
        antialiasing: true,
        pickable: true,
        autoHighlight: true,
        onClick: showObservation,
        stroked: false,
      });

    const map = new window.maplibregl.Map({
      container: element,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [0, -90],
      zoom: 0,
      minZoom: -0.8,
      maxZoom: 6,
      bearing: 0,
      pitch: 0,
      dragPan: true,
      dragRotate: false,
      touchPitch: false,
      attributionControl: true,
    });
    const overlay = new window.deck.MapboxOverlay({
      interleaved: true,
      layers: [],
    });
    entry = { element, source: "", points: [], layer, map, overlay };
    activeMaps.set(element, entry);
    map.addControl(new window.maplibregl.NavigationControl(), "top-right");
    map.addControl(overlay);
    map.on("load", () => {
      try {
        map.setProjection({ type: "globe" });
        map.jumpTo({ center: [0, -85], zoom: -0.3 });
      } catch (error) {
        console.error("Could not initialize the Antarctic globe projection.", error);
        showError(element, "The Antarctic globe projection could not be initialized. Refresh the page to retry.");
        return;
      }
      void setPoints(entry, element.getAttribute("data-globe-source"));
    });
    map.on("error", (event) => {
      if (!map.loaded()) {
        console.error("Could not load the Antarctic basemap.", event.error);
        showError(element, "The coastline basemap could not be loaded. Check network access and refresh.");
      }
    });
  };

  const sync = () => {
    for (const [element, entry] of activeMaps) {
      if (!element.isConnected) {
        entry.overlay.finalize();
        entry.map.remove();
        activeMaps.delete(element);
      }
    }
    document
      .querySelectorAll("[data-globe-source]")
      .forEach((element) => mount(element));
  };

  const observer = new MutationObserver(sync);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-globe-source"],
    childList: true,
    subtree: true,
  });
  sync();
})();
