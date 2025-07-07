# diptank_monitor_app.py
# This script creates a Tkinter desktop application to simulate
# sensor readings and water pump operations for the Diptank project.
# It directly interacts with the Django database.

import tkinter as tk
from tkinter import ttk, messagebox
import os
import django
import threading
import time
import random
from collections import defaultdict

# --- Django Setup (CRITICAL for accessing Django models) ---
# Configure Django settings. This must be done before importing any Django models.
# 'config.settings' refers to your project's settings file (e.g., myproject/settings.py)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Import Django models after setup
from diptank.models import Tank, SensorReading, Alert
from django.db import transaction, OperationalError

# --- Global Variables ---
# Interval for pump simulation updates (in seconds)
PUMP_UPDATE_INTERVAL = 1.0
# Amount of water added/removed per pump update (in Liters)
PUMP_FLOW_RATE = 50.0
# Flag to control the pump simulation thread
pump_running = False
pump_thread = None
selected_tank_id = None  # To store the currently selected tank's ID


class DiptankMonitorApp:
    def __init__(self, master):
        self.master = master
        master.title("Diptank Sensor & Pump Monitor")

        # Set the window to fullscreen
        master.attributes('-fullscreen', True)

        # Apply a modern style to Tkinter widgets
        style = ttk.Style()
        style.theme_use('clam')  # 'clam', 'alt', 'default', 'classic'

        style.configure('TFrame', background='#f0f2f5')
        style.configure('TLabel', background='#f0f2f5', foreground='#333', font=('Inter', 10))
        style.configure('TButton', font=('Inter', 10, 'bold'), padding=10, relief='flat',
                        background='#3b82f6', foreground='white')
        style.map('TButton', background=[('active', '#2563eb')])
        style.configure('TCombobox', font=('Inter', 10), fieldbackground='white', background='white')
        style.configure('TProgressbar', thickness=20, troughcolor='#e0e0e0',
                        background='#3b82f6', borderwidth=0, relief='flat')

        # --- Main Frame (Scrollable) ---
        # Create a Canvas widget to hold the scrollable frame
        self.canvas = tk.Canvas(master, bg='#f0f2f5')
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Add a scrollbar to the canvas
        self.scrollbar = ttk.Scrollbar(master, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # Create a frame inside the canvas to hold the content
        self.main_frame = ttk.Frame(self.canvas, padding="20", style='TFrame')
        self.canvas.create_window((0, 0), window=self.main_frame, anchor="nw", tags="self.main_frame")

        # Bind the frame to resize with the canvas
        self.main_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind('<Configure>', self._on_canvas_resize)

        # --- Tank Selection ---
        ttk.Label(self.main_frame, text="Select Tank:", font=('Inter', 12, 'bold')).pack(pady=(10, 5))
        self.tank_selector = ttk.Combobox(self.main_frame, state="readonly", width=40)
        self.tank_selector.pack(pady=5)
        self.tank_selector.bind("<<ComboboxSelected>>", self.on_tank_selected)

        # --- Selected Tank Information Display ---
        self.info_frame = ttk.LabelFrame(self.main_frame, text="Selected Tank Information", padding="15",
                                         style='TFrame')
        self.info_frame.pack(pady=15, fill=tk.X)

        self.tank_id_label = ttk.Label(self.info_frame, text="ID: N/A")
        self.tank_id_label.pack(anchor='w', pady=2)
        self.location_label = ttk.Label(self.info_frame, text="Location: N/A")
        self.location_label.pack(anchor='w', pady=2)
        self.capacity_label = ttk.Label(self.info_frame, text="Capacity: N/A L")
        self.capacity_label.pack(anchor='w', pady=2)
        self.current_level_label = ttk.Label(self.info_frame, text="Current Level: N/A L (N/A%)")
        self.current_level_label.pack(anchor='w', pady=2)
        self.min_threshold_label = ttk.Label(self.info_frame, text="Min Threshold: N/A%")
        self.min_threshold_label.pack(anchor='w', pady=2)
        self.max_threshold_label = ttk.Label(self.info_frame, text="Max Threshold: N/A%")
        self.max_threshold_label.pack(anchor='w', pady=2)
        self.status_label = ttk.Label(self.info_frame, text="Status: N/A", font=('Inter', 10, 'bold'))
        self.status_label.pack(anchor='w', pady=5)

        # Water Level Progress Bar for Selected Tank
        self.progress_frame = ttk.Frame(self.info_frame, style='TFrame')
        self.progress_frame.pack(pady=10, fill=tk.X)
        ttk.Label(self.progress_frame, text="Water Level:").pack(side=tk.LEFT, padx=(0, 5))
        self.water_level_progress = ttk.Progressbar(self.progress_frame, orient="horizontal", length=200,
                                                    mode="determinate")
        self.water_level_progress.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- Sensor & Pump Controls ---
        self.controls_frame = ttk.LabelFrame(self.main_frame, text="Controls", padding="15", style='TFrame')
        self.controls_frame.pack(pady=15, fill=tk.X)

        self.simulate_button = ttk.Button(self.controls_frame, text="Simulate Sensor Reading",
                                          command=self.simulate_sensor_reading)
        self.simulate_button.pack(pady=5, fill=tk.X)

        self.pump_status_label = ttk.Label(self.controls_frame, text="Pump: OFF", font=('Inter', 11, 'bold'),
                                           foreground='red')
        self.pump_status_label.pack(pady=(10, 5))

        self.pump_on_button = ttk.Button(self.controls_frame, text="Turn Pump ON",
                                         command=lambda: self.toggle_pump(True, manual_override=True))
        self.pump_on_button.pack(side=tk.LEFT, expand=True, padx=5, fill=tk.X)
        self.pump_off_button = ttk.Button(self.controls_frame, text="Turn Pump OFF",
                                          command=lambda: self.toggle_pump(False, manual_override=True))
        self.pump_off_button.pack(side=tk.RIGHT, expand=True, padx=5, fill=tk.X)

        # --- Overall Water Levels (All Tanks) Display ---
        self.overall_all_tanks_frame = ttk.LabelFrame(self.main_frame, text="Overall Water Levels (All Tanks)",
                                                      padding="15", style='TFrame')
        self.overall_all_tanks_frame.pack(pady=15, fill=tk.X)

        self.overall_volume_label = ttk.Label(self.overall_all_tanks_frame,
                                              text="Total Volume: N/A L / Total Capacity: N/A L")
        self.overall_volume_label.pack(anchor='w', pady=2)
        self.overall_percentage_label = ttk.Label(self.overall_all_tanks_frame, text="Overall Percentage: N/A%")
        self.overall_percentage_label.pack(anchor='w', pady=2)
        self.overall_status_label = ttk.Label(self.overall_all_tanks_frame, text="Overall Status: N/A",
                                              font=('Inter', 10, 'bold'))
        self.overall_status_label.pack(anchor='w', pady=5)

        # Overall Water Level Progress Bar (All Tanks)
        self.overall_progress_frame = ttk.Frame(self.overall_all_tanks_frame, style='TFrame')
        self.overall_progress_frame.pack(pady=10, fill=tk.X)
        ttk.Label(self.overall_progress_frame, text="Overall Level:").pack(side=tk.LEFT, padx=(0, 5))
        self.overall_water_level_progress = ttk.Progressbar(self.overall_progress_frame, orient="horizontal",
                                                            length=200, mode="determinate")
        self.overall_water_level_progress.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- Overall Water Levels by Location Display ---
        self.overall_by_location_container_frame = ttk.LabelFrame(self.main_frame,
                                                                  text="Overall Water Levels by Location", padding="15",
                                                                  style='TFrame')
        self.overall_by_location_container_frame.pack(pady=15, fill=tk.X)

        # This frame will hold the dynamically generated location-specific summaries
        self.overall_by_location_frames = {}  # Dictionary to hold location frames for easy update/removal

        # --- Status Message ---
        self.status_message = ttk.Label(self.main_frame, text="", foreground='blue', font=('Inter', 10))
        self.status_message.pack(pady=10)

        # Load tanks on startup
        self._load_tanks_and_init_selection()

    def _on_canvas_resize(self, event):
        """Adjusts the main_frame width to match the canvas width."""
        self.canvas.itemconfig("self.main_frame", width=event.width)

    def _load_tanks_and_init_selection(self):
        """Fetches tanks from the database and populates the dropdown."""
        try:
            tanks = Tank.objects.all().order_by('location', 'tank_id')
            self.tank_map = {f"Tank {t.tank_id} - {t.location}": t.tank_id for t in tanks}
            self.tank_selector['values'] = list(self.tank_map.keys())
            if tanks:
                # Select the first tank by default
                first_tank_display = list(self.tank_map.keys())[0]
                self.tank_selector.set(first_tank_display)
                self.on_tank_selected(None)  # Manually trigger update for the first tank
            else:
                self.status_message.config(
                    text="No tanks found in the database. Please register tanks via Django admin or officer dashboard.")
                self._clear_selected_tank_display()
        except OperationalError as e:
            messagebox.showerror("Database Error", f"Could not connect to database or tables are not ready: {e}\n"
                                                   "Please ensure your Django migrations are applied and the database is accessible.")
            self._clear_selected_tank_display()
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred while loading tanks: {e}")
            self._clear_selected_tank_display()
        finally:
            self._update_all_displays()  # Always update all displays after loading tanks

    def _clear_selected_tank_display(self):
        """Clears all selected tank information labels."""
        self.tank_id_label.config(text="ID: N/A")
        self.location_label.config(text="Location: N/A")
        self.capacity_label.config(text="Capacity: N/A L")
        self.current_level_label.config(text="Current Level: N/A L (N/A%)")
        self.min_threshold_label.config(text="Min Threshold: N/A%")
        self.max_threshold_label.config(text="Max Threshold: N/A%")
        self.status_label.config(text="Status: N/A", foreground='black')
        self.water_level_progress['value'] = 0
        self.tank_selector.set("")
        global selected_tank_id
        selected_tank_id = None
        self.toggle_pump(False, manual_override=False)  # Ensure pump is off when no tank is selected

    def on_tank_selected(self, event):
        """Updates the display when a new tank is selected."""
        global selected_tank_id
        selected_display_name = self.tank_selector.get()
        selected_tank_id = self.tank_map.get(selected_display_name)
        self._update_all_displays()
        # Immediately check pump status based on thresholds when a tank is selected
        self.master.after(100, self._check_and_toggle_pump_auto)  # Small delay to ensure display updates

    def _update_all_displays(self):
        """Updates all relevant display sections."""
        self._update_selected_tank_display()
        self._update_overall_summary_display()
        self._update_overall_by_location_display()

    def _update_selected_tank_display(self):
        """Fetches the latest data for the selected tank and updates its UI."""
        global selected_tank_id
        if selected_tank_id:
            try:
                tank = Tank.objects.get(pk=selected_tank_id)
                self.tank_id_label.config(text=f"ID: {tank.tank_id}")
                self.location_label.config(text=f"Location: {tank.location}")
                self.capacity_label.config(text=f"Capacity: {tank.capacity:.2f} L")

                current_percentage = (tank.current_level / tank.capacity) * 100 if tank.capacity > 0 else 0
                self.current_level_label.config(
                    text=f"Current Level: {tank.current_level:.2f} L ({current_percentage:.0f}%)")
                self.min_threshold_label.config(text=f"Min Threshold: {tank.min_threshold:.0f}%")
                self.max_threshold_label.config(text=f"Max Threshold: {tank.max_threshold:.0f}%")

                # Update status and progress bar color
                status = 'Optimal'
                status_color = 'green'
                if current_percentage < tank.min_threshold:
                    status = 'Low'
                    status_color = 'orange'
                elif current_percentage > tank.max_threshold:
                    status = 'High'
                    status_color = 'red'
                self.status_label.config(text=f"Status: {status}", foreground=status_color)

                self.water_level_progress['value'] = current_percentage

                self.status_message.config(text=f"Tank {tank.tank_id} data refreshed.")

            except Tank.DoesNotExist:
                self.status_message.config(text="Selected tank not found in database.", foreground='red')
                self._clear_selected_tank_display()
            except OperationalError as e:
                messagebox.showerror("Database Error", f"Could not refresh tank data: {e}\n"
                                                       "Please ensure your Django migrations are applied and the database is accessible.")
                self._clear_selected_tank_display()
            except Exception as e:
                messagebox.showerror("Error", f"An unexpected error occurred while updating tank display: {e}")
                self._clear_selected_tank_display()
        else:
            self._clear_selected_tank_display()
            self.status_message.config(text="No tank selected.", foreground='blue')

    def _update_overall_summary_display(self):
        """Calculates and displays the overall water levels across all tanks."""
        try:
            all_tanks = Tank.objects.all()
            total_current_water_volume = sum(tank.current_level for tank in all_tanks)
            total_tank_capacity = sum(tank.capacity for tank in all_tanks)

            if total_tank_capacity > 0:
                overall_percentage = (total_current_water_volume / total_tank_capacity) * 100
            else:
                overall_percentage = 0

            overall_status = 'Optimal'
            overall_status_color = 'green'
            if overall_percentage < 20:  # Example global low threshold
                overall_status = 'Critical'
                overall_status_color = 'red'
            elif overall_percentage < 50:  # Example global warning threshold
                overall_status = 'Low'
                overall_status_color = 'orange'

            self.overall_volume_label.config(
                text=f"Total Volume: {total_current_water_volume:.2f} L / Total Capacity: {total_tank_capacity:.2f} L")
            self.overall_percentage_label.config(text=f"Overall Percentage: {overall_percentage:.0f}%")
            self.overall_status_label.config(text=f"Overall Status: {overall_status}", foreground=overall_status_color)
            self.overall_water_level_progress['value'] = overall_percentage

        except OperationalError as e:
            print(f"Database error while updating overall display: {e}")
            self.overall_volume_label.config(text="Total Volume: N/A L / Total Capacity: N/A L")
            self.overall_percentage_label.config(text="Overall Percentage: N/A%")
            self.overall_status_label.config(text="Overall Status: Error", foreground='red')
            self.overall_water_level_progress['value'] = 0
        except Exception as e:
            print(f"An unexpected error occurred while updating overall display: {e}")
            self.overall_volume_label.config(text="Total Volume: N/A L / Total Capacity: N/A L")
            self.overall_percentage_label.config(text="Overall Percentage: N/A%")
            self.overall_status_label.config(text="Overall Status: Error", foreground='red')
            self.overall_water_level_progress['value'] = 0

    def _update_overall_by_location_display(self):
        """Calculates and displays overall water levels for each unique location."""
        # Clear existing location frames
        for frame in self.overall_by_location_frames.values():
            frame.destroy()
        self.overall_by_location_frames.clear()

        try:
            all_tanks = Tank.objects.all()

            # Aggregate data by location
            location_data = defaultdict(lambda: {'current_level': 0.0, 'capacity': 0.0})
            for tank in all_tanks:
                location_data[tank.location]['current_level'] += tank.current_level
                location_data[tank.location]['capacity'] += tank.capacity

            # Sort locations alphabetically
            sorted_locations = sorted(location_data.keys())

            if not sorted_locations:
                no_tanks_label = ttk.Label(self.overall_by_location_container_frame,
                                           text="No tanks found to display by location.", foreground='gray')
                no_tanks_label.pack(pady=10)
                return

            for location in sorted_locations:
                data = location_data[location]
                loc_current_volume = data['current_level']
                loc_capacity = data['capacity']

                if loc_capacity > 0:
                    loc_percentage = (loc_current_volume / loc_capacity) * 100
                else:
                    loc_percentage = 0

                loc_status = 'Optimal'
                loc_status_color = 'green'
                if loc_percentage < 20:  # Using same example thresholds as overall_summary
                    loc_status = 'Critical'
                    loc_status_color = 'red'
                elif loc_percentage < 50:
                    loc_status = 'Low'
                    loc_status_color = 'orange'

                # Create a new frame for this location's summary
                loc_frame = ttk.LabelFrame(self.overall_by_location_container_frame, text=f"Location: {location}",
                                           padding="10", style='TFrame')
                loc_frame.pack(pady=5, fill=tk.X, expand=True)
                self.overall_by_location_frames[location] = loc_frame  # Store reference

                ttk.Label(loc_frame, text=f"Volume: {loc_current_volume:.2f} L / Capacity: {loc_capacity:.2f} L").pack(
                    anchor='w', pady=1)
                ttk.Label(loc_frame, text=f"Percentage: {loc_percentage:.0f}%").pack(anchor='w', pady=1)
                ttk.Label(loc_frame, text=f"Status: {loc_status}", font=('Inter', 9, 'bold'),
                          foreground=loc_status_color).pack(anchor='w', pady=3)

                # Progress bar for location
                loc_progress_frame = ttk.Frame(loc_frame, style='TFrame')
                loc_progress_frame.pack(pady=5, fill=tk.X)
                ttk.Label(loc_progress_frame, text="Level:").pack(side=tk.LEFT, padx=(0, 5))
                loc_progress_bar = ttk.Progressbar(loc_progress_frame, orient="horizontal", length=150,
                                                   mode="determinate")
                loc_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
                loc_progress_bar['value'] = loc_percentage

        except OperationalError as e:
            error_label = ttk.Label(self.overall_by_location_container_frame,
                                    text=f"Database error loading location data: {e}", foreground='red')
            error_label.pack(pady=10)
            print(f"Database error while updating overall by location display: {e}")
        except Exception as e:
            error_label = ttk.Label(self.overall_by_location_container_frame, text=f"An unexpected error occurred: {e}",
                                    foreground='red')
            error_label.pack(pady=10)
            print(f"An unexpected error occurred while updating overall by location display: {e}")

    def simulate_sensor_reading(self):
        """Simulates a sensor reading and updates the tank level in the database."""
        global selected_tank_id
        if not selected_tank_id:
            messagebox.showwarning("No Tank Selected", "Please select a tank first.")
            return

        try:
            with transaction.atomic():  # Ensure atomicity for database operations
                tank = Tank.objects.select_for_update().get(pk=selected_tank_id)  # Lock the row for update

                # Simulate a new water level (e.g., random fluctuation around current level)
                # Ensure it stays within 0 and capacity
                fluctuation = random.uniform(-0.05, 0.05) * tank.capacity  # +/- 5% of capacity
                new_level = tank.current_level + fluctuation
                new_level = max(0.0, min(tank.capacity, new_level))  # Clamp between 0 and capacity

                # Update tank's current level
                tank.current_level = new_level
                tank.save()

                # Create a new sensor reading record
                SensorReading.objects.create(
                    tank=tank,
                    water_level=new_level
                )

                # Check for alerts based on new level
                current_percentage = (new_level / tank.capacity) * 100 if tank.capacity > 0 else 0
                if current_percentage < tank.min_threshold:
                    Alert.objects.create(
                        tank=tank,
                        alert_type='low_water',
                        message=f"Tank {tank.tank_id} at {tank.location} is below minimum threshold ({tank.min_threshold:.0f}%). Current: {current_percentage:.0f}%"
                    )
                    self.status_message.config(text=f"Alert: Low water level for Tank {tank.tank_id}!",
                                               foreground='red')
                elif current_percentage > tank.max_threshold:
                    Alert.objects.create(
                        tank=tank,
                        alert_type='high_water',
                        message=f"Tank {tank.tank_id} at {tank.location} is above maximum threshold ({tank.max_threshold:.0f}%). Current: {current_percentage:.0f}%"
                    )
                    self.status_message.config(text=f"Alert: High water level for Tank {tank.tank_id}!",
                                               foreground='red')
                else:
                    self.status_message.config(
                        text=f"Sensor reading simulated for Tank {tank.tank_id}. Level: {new_level:.2f}L",
                        foreground='green')

                self._update_all_displays()  # Refresh all displays immediately
                self._check_and_toggle_pump_auto()  # Check pump status after simulation

        except Tank.DoesNotExist:
            messagebox.showerror("Error", "Selected tank not found.")
            self.status_message.config(text="Error: Selected tank not found.", foreground='red')
        except OperationalError as e:
            messagebox.showerror("Database Error", f"Could not simulate reading: {e}\n"
                                                   "Ensure your Django migrations are applied and the database is accessible.")
            self.status_message.config(text="Database error during simulation.", foreground='red')
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred during sensor simulation: {e}")
            self.status_message.config(text="An unexpected error occurred.", foreground='red')

    def toggle_pump(self, turn_on, manual_override=False):
        """Starts or stops the pump simulation. Can be called manually or automatically."""
        global pump_running, pump_thread, selected_tank_id

        if not selected_tank_id:
            if manual_override:  # Only show warning if user manually tried to toggle
                messagebox.showwarning("No Tank Selected", "Please select a tank first to control the pump.")
            return

        if turn_on and not pump_running:
            pump_running = True
            self.pump_status_label.config(text="Pump: ON", foreground='green')
            self.pump_on_button.config(state=tk.DISABLED)
            self.pump_off_button.config(state=tk.NORMAL)
            if manual_override:
                self.status_message.config(text="Pump manually turned ON.", foreground='green')
            else:
                self.status_message.config(text="Pump automatically turned ON (Low Level).", foreground='green')
            pump_thread = threading.Thread(target=self._pump_simulation_loop, daemon=True)
            pump_thread.start()
        elif not turn_on and pump_running:
            pump_running = False
            # No need to join thread explicitly, daemon=True will clean it up on app exit
            self.pump_status_label.config(text="Pump: OFF", foreground='red')
            self.pump_on_button.config(state=tk.NORMAL)
            self.pump_off_button.config(state=tk.DISABLED)
            if manual_override:
                self.status_message.config(text="Pump manually turned OFF.", foreground='blue')
            else:
                self.status_message.config(text="Pump automatically turned OFF (Optimal Level).", foreground='blue')

    def _check_and_toggle_pump_auto(self):
        """Checks tank thresholds and automatically toggles pump if needed."""
        global selected_tank_id, pump_running
        if selected_tank_id:
            try:
                tank = Tank.objects.get(pk=selected_tank_id)
                current_percentage = (tank.current_level / tank.capacity) * 100 if tank.capacity > 0 else 0

                if current_percentage < tank.min_threshold and not pump_running:
                    self.toggle_pump(True, manual_override=False)  # Auto turn ON
                elif current_percentage >= tank.max_threshold and pump_running:
                    self.toggle_pump(False, manual_override=False)  # Auto turn OFF
            except Tank.DoesNotExist:
                # Tank might have been deleted, stop pump
                self.toggle_pump(False, manual_override=False)
            except OperationalError as e:
                # Handle database errors gracefully, stop pump if necessary
                print(f"Database error during auto pump check: {e}")
                self.toggle_pump(False, manual_override=False)
            except Exception as e:
                print(f"An unexpected error occurred during auto pump check: {e}")
                self.toggle_pump(False, manual_override=False)

    def _pump_simulation_loop(self):
        """Background thread for pump simulation."""
        global pump_running, selected_tank_id, PUMP_FLOW_RATE

        while pump_running:
            if selected_tank_id:
                try:
                    with transaction.atomic():  # Ensure atomicity
                        tank = Tank.objects.select_for_update().get(pk=selected_tank_id)

                        current_percentage = (tank.current_level / tank.capacity) * 100 if tank.capacity > 0 else 0

                        # Auto-stop if max threshold is hit during pumping
                        if current_percentage >= tank.max_threshold:
                            self.master.after(0, lambda: self.toggle_pump(False, manual_override=False))
                            self.master.after(0, lambda: self.status_message.config(
                                text=f"Pump auto-stopped for Tank {tank.tank_id} (Max Threshold Reached).",
                                foreground='blue'))
                            break  # Exit loop if pump is stopped

                        # Simulate pumping water IN (increase level)
                        new_level = tank.current_level + PUMP_FLOW_RATE
                        new_level = min(tank.capacity, new_level)  # Don't exceed capacity

                        tank.current_level = new_level
                        tank.save()

                        # Create a sensor reading for the pump action
                        SensorReading.objects.create(
                            tank=tank,
                            water_level=new_level
                        )

                        # Update UI on the main thread
                        self.master.after(0, self._update_all_displays)  # Call the new consolidated update
                        self.master.after(0, lambda: self.status_message.config(
                            text=f"Pump active for Tank {tank.tank_id}. Level: {new_level:.2f}L", foreground='blue'))

                        # Check for alerts (e.g., if pump overfills, though auto-stop should prevent this)
                        current_percentage = (new_level / tank.capacity) * 100 if tank.capacity > 0 else 0
                        if current_percentage > tank.max_threshold:
                            # This alert should ideally not be triggered if auto-stop works, but as a fallback
                            Alert.objects.create(
                                tank=tank,
                                alert_type='high_water',
                                message=f"Tank {tank.tank_id} at {tank.location} is above maximum threshold ({tank.max_threshold:.0f}%). Current: {current_percentage:.0f}% due to pump."
                            )
                            self.master.after(0, lambda: self.status_message.config(
                                text=f"Alert: Pump overfilled Tank {tank.tank_id}!", foreground='red'))
                            self.master.after(0, lambda: self.toggle_pump(False,
                                                                          manual_override=False))  # Ensure pump stops
                            break  # Exit loop if pump is stopped

                except Tank.DoesNotExist:
                    self.master.after(0, lambda: messagebox.showerror("Error",
                                                                      "Selected tank not found during pump operation."))
                    self.master.after(0, lambda: self.toggle_pump(False,
                                                                  manual_override=False))  # Stop pump if tank disappears
                    break  # Exit loop
                except OperationalError as e:
                    self.master.after(0, lambda: messagebox.showerror("Database Error",
                                                                      f"Could not update tank during pump operation: {e}"))
                    self.master.after(0,
                                      lambda: self.toggle_pump(False, manual_override=False))  # Stop pump on DB error
                    break  # Exit loop
                except Exception as e:
                    self.master.after(0, lambda: messagebox.showerror("Error",
                                                                      f"An unexpected error occurred during pump simulation: {e}"))
                    self.master.after(0,
                                      lambda: self.toggle_pump(False, manual_override=False))  # Stop pump on any error
                    break  # Exit loop

            time.sleep(PUMP_UPDATE_INTERVAL)


# --- Main application entry point. ---
if __name__ == "__main__":
    root = tk.Tk()
    app = DiptankMonitorApp(root)
    root.mainloop()


