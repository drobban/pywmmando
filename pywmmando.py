#!/usr/bin/env python3.11
"""
Simple dockapp to show response time from logged services
also signal up/down state
"""
import argparse
import os
import time
import json
from datetime import datetime
import requests

import wmdocklib
from wmdocklib import helpers
from wmdocklib import pywmgeneral


XDG_CONF_DIR = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
# expected bitmap contained font should be found in the same location as main
# program
with open(os.path.dirname(__file__) + "/background.xpm", "r") as fo:
    BACKGROUND = "".join(fo.readlines())

with open(os.path.dirname(__file__) + "/font.xpm", "r") as fo:
    FONT = "".join(fo.readlines())


def aggregate_hourly(collection):
    collection.sort(key=lambda state: datetime.fromisoformat(state["inserted"]))
    hourly = {}
    for state in collection:
        key = state["inserted"][:13]
        if key in hourly:
            hourly[key]["tot_time"] += state["time"]
            hourly[key]["tot"] += 1
            hourly[key]["avg_time"] = hourly[key]["tot_time"] / hourly[key]["tot"]
            hourly[key]["online"] = state["online"] == "true"
        else:
            hourly[key] = {
                "tot_time": state["time"],
                "tot": 1,
                "avg_time": state["time"],
                "online": state["online"] == "true",
            }

    aggregated = [(key + ":00:00Z", val) for key, val in hourly.items()]
    return (collection[-1]["online"], aggregated)


# returns aggregated data from state json from monitor service
def process_json(path):
    r = requests.get(path)

    data = json.loads(r.content)["data"]

    return data


# return min max tuple from hourly data
def min_max(hour_data):
    avg_times = [hour["avg_time"] for (time, hour) in hour_data]
    return (min(avg_times), max(avg_times))


def scale(hour_data):
    if len(hour_data):
        (min_val, max_val) = min_max(hour_data)
        scale = 100 / (min(max_val, min_val * 10) - min_val)
    else:
        scale = 1

    return scale


class MandoDockApp(wmdocklib.DockApp):
    background_color = "#202020"
    graph_width = 58
    graph_max_height = 36
    graph_coords = (3, 25)

    def __init__(self, args=None):
        super().__init__(args)
        # self._debug = args.debug
        self.name = args.name
        self.service = args.service
        self.endpoint = args.endpoint
        self.fonts = [wmdocklib.BitmapFonts(FONT, (6, 8))]
        self.background = BACKGROUND
        self.conf = {}
        self.critical = 0
        self.warning = 0
        self._read_config()
        self._current_graph = "efs"
        self._history = {}
        self.aggregated = []
        self.online = False
        self.time_val = 0
        helpers.add_mouse_region(
            0,
            self.graph_coords[0],
            self.graph_coords[1],
            width=self.graph_width,
            height=self.graph_max_height,
        )

    def run(self):
        self.prepare_pixmaps()
        self.open_xwindow()
        try:
            self.main_loop()
        except KeyboardInterrupt:
            pass

    def main_loop(self):

        count = 0
        while True:
            self._on_event(self.check_for_events())
            color_setting = 0
            if self.online:
                color_setting = 0
            elif not self.online:
                color_setting = 2

            self._put_string(self.name, v_pos=1, color_setting=color_setting)

            self._put_string(
                str(int(self.time_val)) + " ms",
                h_pos=9,
                v_pos=1,
                color_setting=color_setting,
            )

            self._draw_graph()

            self._draw_graph_label(color_setting=color_setting)
            self.redraw()
            count += 1

            if count >= 50:
                # Fetch data and update history graph
                self._update_history()
                count = 0

            time.sleep(0.1)

    def _read_config(self):
        self.conf = {"url": "test.com", "name": "test000"}

    def _on_event(self, event):
        if not event:
            return

        if event.get("type") == "buttonrelease" and event.get("button") == 1:
            x = event.get("x", 0)
            y = event.get("y", 0)
            region = helpers.check_mouse_region(x, y)
            if helpers.check_mouse_region(x, y) > -1:
                os.system("xmessage action 1")
            elif helpers.check_mouse_region(x, y) == -1:
                os.system("xmessage action 0")

            print(f"{helpers.check_mouse_region(x, y)}")

            return True

    def _put_string(self, item, h_pos=1, v_pos=1, color_setting=0):
        name = item.upper()[:9]
        color_offset = 2
        color = max(
            int(
                (self.fonts[0].charset_width / self.fonts[0].width)
                * color_setting
                * color_offset
            ),
            0,
        )
        name = "".join([chr(ord(i) + color) for i in name])

        self.fonts[0].add_string(name, v_pos, h_pos)

    def _update_history(self):
        new_data = {h["inserted"]: h for h in process_json(self.endpoint)}
        self._history = {**self._history, **new_data}
        print(f"len:{len(self._history)}")
        print(f"type:{type(self._history)}")

        distinct = [val for key, val in self._history.items()]
        (self.online, self.aggregated) = aggregate_hourly(distinct)[:58]
        self.time_val = self.aggregated[-1][1]["avg_time"]

    def _draw_graph(self):
        data = self.aggregated
        time_scale = scale(data)

        for count, (_hour, item) in enumerate(data):
            # height = int((item / 100) * self.graph_max_height)
            height = int(
                (item["avg_time"] * time_scale) * (self.graph_max_height / 100)
            )
            helpers.copy_xpm_area(
                65,
                self.graph_coords[1],
                1,
                self.graph_max_height,
                self.graph_coords[0] + count,
                self.graph_coords[1],
            )
            helpers.copy_xpm_area(
                64,
                self.graph_coords[1],
                1,
                self.graph_max_height - height,
                self.graph_coords[0] + count,
                self.graph_coords[1],
            )

    def _draw_graph_label(self, color_setting=0):
        name = self.service.upper()
        helpers.copy_xpm_area(1, 65, len(name) * self.fonts[0].width + 1, 1, 4, 51)
        helpers.copy_xpm_area(1, 65, 1, self.fonts[0].height + 1, 4, 51)

        color_offset = 2
        color = max(
            int(
                (self.fonts[0].charset_width / self.fonts[0].width)
                * color_setting
                * color_offset
            ),
            0,
        )
        name = "".join([chr(ord(i) + color) for i in name])

        self.fonts[0].add_string(name, 2, 49)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="Alternate config file")
    parser.add_argument("-n", "--name", help="Name")
    parser.add_argument("-s", "--service", help="Service name")
    parser.add_argument("-e", "--endpoint", help="API endpoint for data")
    parser.add_argument("-a1", "--action1", help="Shell command to top click")
    parser.add_argument("-a0", "--action0", help="Shell command to bottom click")
    args = parser.parse_args()

    dockapp = MandoDockApp(args)
    dockapp.run()


if __name__ == "__main__":
    main()
