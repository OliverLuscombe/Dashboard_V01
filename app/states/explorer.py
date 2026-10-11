import reflex as rx
import reflex_xy as xy
import asyncio
import math
from faker import Faker


class Explorer(rx.State):
    page: str = "Overview"
    month: int = 9
    year: str = "2023"
    layers: list[str] = ["Sea ice concentration", "Marginal Ice Zone"]
    region: str = ""
    locked: bool = False
    zoom: float = 1.0
    pan: int = 0
    playing: bool = False
    split: bool = False
    divider: int = 50
    compare_year: str = "2017"
    compare_month: str = "February"
    variable_a: str = "Sea-surface temperature (°C)"
    variable_b: str = "Sea ice concentration (%)"
    cluster: int = 2
    display: str = "Standard"
    display_open: bool = False
    metadata: str = ""
    notice: str = ""
    months: list[str] = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    layer_names: list[str] = [
        "Sea ice concentration",
        "Marginal Ice Zone",
        "Sea-surface temperature",
        "Wind speed",
        "Air temperature",
        "ML clusters",
    ]
    regions: list[str] = [
        "Weddell Sea",
        "East Antarctica",
        "Ross Sea",
        "Amundsen Sea",
    ]
    variables: list[str] = [
        "Sea-surface temperature (°C)",
        "Sea ice concentration (%)",
        "Wind speed (m/s)",
        "Air temperature (°C)",
    ]

    @rx.var
    def date(self) -> str:
        names = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        return f"{names[self.month - 1]} {self.year}"

    @rx.var
    def extent(self) -> float:
        return [
            4.6,
            2.8,
            4.1,
            7.2,
            10.4,
            13.5,
            15.6,
            17.0,
            17.2,
            15.7,
            11.2,
            6.9,
        ][self.month - 1] + (int(self.year) - 2023) * 0.12

    @rx.var
    def miz(self) -> float:
        return self.extent * 0.105

    @rx.var
    def concentration(self) -> float:
        return (
            44
            + self.extent * 1.8
            + (
                self.regions.index(self.region) * 3
                if self.region in self.regions
                else 0
            )
        )

    @rx.var
    def temperature(self) -> float:
        return -0.2 - self.extent * 0.08

    @rx.var
    def wind(self) -> float:
        return 7.5 + self.extent * 0.28 + self.cluster * 0.3

    @rx.event
    def navigate(self, page: str):
        self.page = page
        self.playing = False
        if page == "Model Insights" and "ML clusters" not in self.layers:
            self.layers.append("ML clusters")
        if page == "Data":
            from app.states.uploaded_data import UploadedData

            return UploadedData.load_catalogue

    @rx.event
    def set_month(self, value: int):
        self.month = value

    @rx.event
    def scrub(self, value: str):
        self.month = int(value)

    @rx.event
    def set_year(self, value: str):
        self.year = value

    @rx.event
    def step(self, amount: int):
        self.month = (self.month - 1 + amount) % 12 + 1

    @rx.event
    def toggle_play(self):
        self.playing = not self.playing
        if self.playing:
            return Explorer.animate

    @rx.event(background=True)
    async def animate(self):
        for _ in range(24):
            await asyncio.sleep(1.2)
            async with self:
                if not self.playing:
                    return
                self.month = self.month % 12 + 1
        async with self:
            self.playing = False

    @rx.event
    def toggle_layer(self, name: str):
        if name in self.layers:
            self.layers.remove(name)
        else:
            self.layers.append(name)

    @rx.event
    def select_region(self, name: str):
        if not self.locked:
            self.region = name
            self.pan = self.regions.index(name) * 10 - 15

    @rx.event
    def clear_region(self):
        self.locked = False
        self.region = ""
        self.pan = 0

    @rx.event
    def toggle_lock(self):
        self.locked = not self.locked

    @rx.event
    def change_zoom(self, amount: float):
        self.zoom = min(2.3, max(0.8, self.zoom + amount))

    @rx.event
    def reset_view(self):
        self.zoom = 1.0
        self.pan = 0

    @rx.event
    def move(self, amount: int):
        self.pan = min(80, max(-80, self.pan + amount))

    @rx.event
    def toggle_split(self):
        self.split = not self.split

    @rx.event
    def set_divider(self, value: str):
        self.divider = int(value)

    @rx.event
    def select_cluster(self, value: int):
        self.cluster = value
        if "ML clusters" not in self.layers:
            self.layers.append("ML clusters")

    @rx.event
    def show_display(self):
        self.display_open = not self.display_open

    @rx.event
    def set_display(self, value: str):
        self.display = value

    @rx.event
    def set_variable_a(self, value: str):
        self.variable_a = value

    @rx.event
    def set_variable_b(self, value: str):
        self.variable_b = value

    @rx.event
    def set_compare_year(self, value: str):
        self.compare_year = value

    @rx.event
    def set_compare_month(self, value: str):
        self.compare_month = value

    @rx.event
    def dataset_action(self, name: str, action: str):
        self.metadata = name
        self.notice = (
            "This synthetic UI fixture cannot be replaced or edited. Import a CSV in the shared workspace above to create a separate stored dataset; scientific demos remain unchanged."
            if action == "replace"
            else "Synthetic fixture · monthly resolution · illustrative polar grid · no external source or research observations."
        )

    @xy.data
    def trend(self) -> dict[str, list[float]]:
        offset = (int(self.year) - 2023) * 0.12
        return {
            "month": list(range(1, 13)),
            "extent": [
                v + offset
                for v in [
                    4.6,
                    2.8,
                    4.1,
                    7.2,
                    10.4,
                    13.5,
                    15.6,
                    17.0,
                    17.2,
                    15.7,
                    11.2,
                    6.9,
                ]
            ],
        }

    def _points(self) -> dict[str, list[float]]:
        fake = Faker()
        fake.seed_instance(int(self.year) + self.month)
        values: dict[str, list[float]] = {v: [] for v in self.variables}
        for i in range(160):
            t = fake.pyfloat(min_value=-1.9, max_value=2.5, right_digits=3)
            noise = fake.pyfloat(min_value=-18, max_value=18, right_digits=2)
            values[self.variables[0]].append(t)
            values[self.variables[1]].append(
                max(0, min(100, 66 - t * 18 + noise + self.month))
            )
            values[self.variables[2]].append(13 + t * 2 + noise * 0.18)
            values[self.variables[3]].append(-17 + t * 4 + noise * 0.2)
        return {"x": values[self.variable_a], "y": values[self.variable_b]}

    @xy.data
    def scatter(self) -> dict[str, list[float]]:
        return self._points()

    @rx.var
    def correlation(self) -> float:
        points = self._points()
        x, y = points["x"], points["y"]
        mx, my = sum(x) / len(x), sum(y) / len(y)
        return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(
            sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)
        )

    def _ice_path(self, radius: float) -> str:
        points = []
        for i in range(241):
            a = i * math.tau / 240
            r = radius * (
                1
                + 0.065 * math.sin(a * 7)
                + 0.035 * math.sin(a * 19)
                + 0.023 * math.cos(a * 37)
            )
            points.append(
                f"{300 + math.cos(a) * r:.1f},{300 + math.sin(a) * r:.1f}"
            )
        return f"M {' L '.join(points)} Z"

    @rx.var
    def map_svg(self) -> str:
        blue = "#145578" if self.display != "High contrast" else "#082b49"
        radius = 150 + self.extent * 3.5
        svg = [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" role="img" aria-label="Illustrative south-polar Antarctica map with synthetic sea ice and graticules">',
            '<defs><clipPath id="ocean"><circle cx="300" cy="300" r="257"/></clipPath><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><path d="M0 0V7" stroke="#267e9e" stroke-width="2"/></pattern><pattern id="dots" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1.4" fill="#736b9b"/></pattern>',
            f'<clipPath id="left"><rect width="{self.divider * 6}" height="600"/></clipPath><clipPath id="right"><rect x="{self.divider * 6}" width="600" height="600"/></clipPath></defs>',
            '<circle cx="300" cy="300" r="258" fill="#e7f0f4" stroke="#bccfd9"/>',
            f'<g clip-path="url(#ocean)"><g transform="translate({self.pan} 0) translate(300 300) scale({self.zoom}) translate(-300 -300)">',
        ]
        for r in [70, 120, 170, 215, 255]:
            svg.append(
                f'<circle cx="300" cy="300" r="{r}" fill="none" stroke="#b5cbd6" stroke-width="0.7" stroke-dasharray="3 4"/>'
            )
        for degree in range(0, 360, 30):
            a = math.radians(degree)
            svg.append(
                f'<path d="M300 300 L{300 + 257 * math.sin(a):.1f} {300 - 257 * math.cos(a):.1f}" stroke="#b5cbd6" stroke-width="0.7"/>'
            )
        periods = [(radius, "")]
        if self.split:
            other = 160 if self.compare_month == "February" else 209
            other += (int(self.compare_year) - 2023) * 0.4
            periods = [(other, "left"), (radius, "right")]
        for rad, clip in periods:
            svg.append(f'<g clip-path="url(#{clip})">' if clip else "<g>")
            if "Sea ice concentration" in self.layers:
                for scale, fill in [
                    (1.0, "#b5d6e6"),
                    (0.91, "#c8e1ed"),
                    (0.82, "#dbedf4"),
                    (0.73, "#eaf5f8"),
                ]:
                    svg.append(
                        f'<path d="{self._ice_path(rad * scale)}" fill="{fill}" stroke="#ffffff" stroke-width="0.6"/>'
                    )
            if "Marginal Ice Zone" in self.layers:
                svg.append(
                    f'<path d="{self._ice_path(rad)}" fill="none" stroke="{blue}" stroke-width="2" stroke-dasharray="5 3"/><path d="{self._ice_path(rad * 0.965)}" fill="none" stroke="#4099b6" stroke-width="9" stroke-dasharray="1 4" opacity="0.6"/>'
                )
            svg.append("</g>")
        if "Sea-surface temperature" in self.layers:
            svg.append(
                '<path d="M105 210 Q300 25 490 230 Q435 180 420 275 Q270 100 145 275Z" fill="#e9a35c" opacity="0.4" stroke="#ba7132" stroke-dasharray="8 3"/>'
            )
        if "Air temperature" in self.layers:
            svg.append(
                '<path d="M150 400 Q300 510 475 350 L465 420 Q270 565 120 435Z" fill="#8f83b5" opacity="0.4" stroke="#635582" stroke-dasharray="3 4"/>'
            )
        if "ML clusters" in self.layers:
            colors = ["#308c94", "#377fa8", "#8578a6", "#c98742"]
            fills = [colors[0], "url(#hatch)", "url(#dots)", colors[3]]
            for i in range(4):
                a, b = i * math.pi / 2, (i + 1) * math.pi / 2
                x1, y1 = 300 + 201 * math.cos(a), 300 + 201 * math.sin(a)
                x2, y2 = 300 + 201 * math.cos(b), 300 + 201 * math.sin(b)
                dash = ["", "8 3", "2 4", "9 3 2 3"][i]
                svg.append(
                    f'<path d="M300 300L{x1} {y1} A201 201 0 0 1 {x2} {y2}Z" fill="{fills[i]}" fill-opacity="0.35" stroke="{colors[i]}" stroke-width="{3 if self.cluster == i + 1 else 1}" stroke-dasharray="{dash}"/>'
                )
                svg.append(
                    f'<text x="{300 + 175 * math.cos(a + 0.7):.0f}" y="{300 + 175 * math.sin(a + 0.7):.0f}" font-size="15" fill="#17364b">C{i + 1}</text>'
                )
        svg.append(
            '<path d="M286 170 L312 159 337 166 349 180 369 181 379 197 399 202 404 219 423 237 426 259 443 279 439 301 450 316 433 337 438 350 420 373 408 378 397 401 377 408 362 420 344 414 331 427 311 419 301 402 279 405 264 394 249 401 231 390 228 374 210 359 207 338 185 328 174 309 180 293 173 280 156 265 149 244 133 230 125 211 111 197 106 177 115 173 129 190 138 196 147 215 167 225 180 246 194 254 207 252 216 264 232 256 243 234 254 226 252 207 267 193 270 179Z" fill="#fafcfc" stroke="#8ca9b9" stroke-width="1.7"/>'
        )
        svg.append(
            '<path d="M245 236 Q275 284 258 365 M290 183 Q330 285 408 335 M210 280 Q297 290 340 413 M320 220 Q354 272 408 254" fill="none" stroke="#d8e3e9" stroke-width="1.2"/><path d="M215 264 Q238 274 243 297 L205 304 186 289Z M264 392 Q282 356 312 378 L329 413 297 402Z" fill="#e0edf2" stroke="#a7becb" stroke-dasharray="3 2"/>'
        )
        if "Wind speed" in self.layers:
            for x, y in [
                (170, 170),
                (250, 120),
                (360, 120),
                (445, 180),
                (480, 320),
                (385, 466),
                (215, 460),
                (130, 350),
            ]:
                svg.append(
                    f'<path d="M{x} {y}l23 -8m-8 -3 8 3 -4 8" fill="none" stroke="#316b79" stroke-width="2"/>'
                )
        svg.append(
            '<text x="310" y="312" text-anchor="middle" font-family="sans-serif" font-size="15" letter-spacing="4" fill="#425e70">ANTARCTICA</text><circle cx="300" cy="300" r="3" fill="#4d6b7d"/><text x="307" y="289" font-size="9" fill="#627c8c">90°S</text><text x="224" y="182" font-size="11" fill="#537688" transform="rotate(-24 224 182)">Weddell Sea</text><text x="275" y="456" font-size="11" fill="#537688">Ross Sea</text></g></g>'
        )
        for degree in range(0, 360, 30):
            a = math.radians(degree)
            label = f"{degree}°E" if degree <= 180 else f"{360 - degree}°W"
            svg.append(
                f'<text x="{300 + 281 * math.sin(a):.1f}" y="{304 - 281 * math.cos(a):.1f}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#6c8494">{label}</text>'
            )
        if self.split:
            svg.append(
                f'<path d="M{self.divider * 6} 45V555" stroke="#183f57" stroke-width="2"/><circle cx="{self.divider * 6}" cy="300" r="14" fill="white" stroke="#183f57"/><text x="{self.divider * 6}" y="305" text-anchor="middle" fill="#183f57">↔</text>'
            )
        svg.append("</svg>")
        return "".join(svg)
