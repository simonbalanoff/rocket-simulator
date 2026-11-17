"""Portable flight recordings shared by all interfaces."""
import csv
import io
from pathlib import Path


class FlightRecorder:
    def __init__(self):
        self.rows = []

    def record(self, time, telemetry, command, targets, landing_x, surface_y):
        self.rows.append(dict(time=time, **telemetry, phase=command.phase,
                              throttle=command.thrust, torque=command.torque,
                              angle_target=targets.get('angle_target', float('nan')),
                              vy_target=targets.get('vy_target', float('nan')),
                              landing_x=landing_x, surface_y=surface_y))

    def to_csv(self):
        stream = io.StringIO(newline='')
        self.write(stream)
        return stream.getvalue()

    def write(self, stream):
        if not self.rows:
            raise ValueError('Cannot save an empty flight')
        writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
        writer.writeheader()
        writer.writerows(self.rows)

    def save(self, path):
        if not self.rows:
            raise ValueError('Cannot save an empty flight')
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='') as stream:
            self.write(stream)
