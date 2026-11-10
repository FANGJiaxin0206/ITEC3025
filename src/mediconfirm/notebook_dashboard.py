"""Notebook controls for the shared Hong Kong clock, preferences and JSON history."""
import asyncio
import html
import json
from pathlib import Path
import ipywidgets as w
from .core import atomic_json
from .intake_store import _moment
from .email_delivery import EmailDelivery
from .web_settings import DEFAULTS, validate_settings, attach_email_previews, read_history


class NotebookDashboard:
    def __init__(self, app, folder):
        self.app = app
        self.folder = Path(folder)
        self.delivery = EmailDelivery(self.folder.parent)
        self.settings_path = self.folder / 'settings.json'
        self.settings = validate_settings(json.loads(self.settings_path.read_text()) if self.settings_path.exists() else DEFAULTS)
        self.closed = False
        self._updating = False
        self.clock = w.HTML()
        self.automatic = w.Checkbox(value=True, description='Use Hong Kong time to select the schedule', indent=False, layout=w.Layout(width='100%'))
        self.reminders = w.Checkbox(value=self.settings['reminders_enabled'], description='Enable reminders at saved times', indent=False)
        self.repeat = w.BoundedIntText(value=int(self.settings['repeat_seconds']), min=1, max=86399, description='Ask again (s):')
        self.timeout = w.BoundedIntText(value=int(self.settings['timeout_seconds']), min=1, max=86400, description='Timeout (s):')
        self.email = w.Text(value=self.settings['caregiver_email'], description='Family email:', layout=w.Layout(width='100%'))
        self.message = w.HTML()
        save = w.Button(description='Save settings', button_style='success')
        save.on_click(self.save)
        self.history = w.HTML()
        refresh = w.Button(description='Refresh history')
        refresh.on_click(lambda _: self.tick())
        self.time_selector = w.Dropdown(options=sorted({m['time'] for m in app.medications or []}), description='Time:')
        self.time_selector.observe(self._manual, names='value')
        self.automatic.observe(lambda _: self.tick(), names='value')
        restore = w.Button(description='Use automatic time')
        restore.on_click(lambda _: setattr(self.automatic, 'value', True))
        settings = w.VBox([self.automatic, self.reminders, self.repeat, self.timeout, self.email, save, self.message,
            w.HTML('<p>Defaults: ask again after 300 seconds and notify after 600 seconds. Both values can be changed. Configure and enable real email in the website under Me; the Notebook shares those settings.</p>')])
        panels = w.Accordion(children=[settings, w.VBox([refresh, self.history]), w.VBox([self.time_selector, restore])], selected_index=None)
        for index, title in enumerate(['Personal settings', 'History records and notifications', 'Manual schedule selection']):
            panels.set_title(index, title)
        self.widget = w.VBox([self.clock, panels, app])
        self._apply_settings()
        app.observe(self._apply_settings, names='simulation_text')
        self.tick()
        try:
            self.task = asyncio.get_running_loop().create_task(self._run())
        except RuntimeError:
            self.task = None

    def _apply_settings(self, change=None):
        self.app.confirmation_repeat_seconds = self.settings['repeat_seconds']
        self.app.confirmation_timeout_seconds = self.settings['timeout_seconds']
        self.app._normal_confirmation_timeout_seconds = self.settings['timeout_seconds']

    def _manual(self, change):
        if self._updating or not change['new']:
            return
        self.automatic.value = False
        self.app.set_check_time(change['new'])

    def save(self, _=None):
        try:
            settings = validate_settings(dict(real_email_enabled=self.settings.get('real_email_enabled',False),timeout_seconds=self.timeout.value, repeat_seconds=self.repeat.value,
                reminders_enabled=self.reminders.value, caregiver_email=self.email.value))
            atomic_json(self.settings_path, settings)
            self.settings = settings
            self._apply_settings()
            self.message.value = 'Settings saved. Existing event deadlines are unchanged. Real email follows the shared website setting.'
            self.tick()
        except (ValueError, OSError) as exc:
            self.message.value = html.escape(str(exc))

    def set_medications(self, medications):
        self.app.medications = medications
        self.app._invalidate_verification()
        self._updating = True
        self.time_selector.options = sorted({m['time'] for m in medications})
        self._updating = False
        self.tick()

    def tick(self):
        if self.closed or self.app._processing:
            return
        if self.settings_path.exists():
            saved = validate_settings(json.loads(self.settings_path.read_text()))
            if saved != self.settings:
                self.settings = saved
                self.timeout.value = int(saved['timeout_seconds'])
                self.repeat.value = int(saved['repeat_seconds'])
                self.email.value = saved['caregiver_email']
                self.reminders.value = saved['reminders_enabled']
                self._apply_settings()
        moment = _moment(None)
        a = self.app
        times = sorted({m['time'] for m in a.medications or []})
        if self.automatic.value and not a._simulation and not a._blocked and not a.has_current_photo and times:
            past = [t for t in times if t <= moment.strftime('%H:%M')]
            selected = past[-1] if past else times[0]
            if a.selected_time != selected:
                a.set_check_time(selected)
        self.clock.value = '<p><b>Hong Kong time:</b> '+moment.strftime('%d %b %Y %H:%M:%S')+' &nbsp; <b>Checking schedule:</b> '+html.escape(a.selected_time)+ (' (selected schedule)' if a._simulation or not self.automatic.value else ' (automatic)')+'</p>'
        if self.settings['reminders_enabled'] and not a._simulation and not a._blocked:
            due = moment.strftime('%H:%M')
            if due in times:
                from .plan_actions import process_plan
                _, _, reminders = process_plan(a.log_path, a.medications, due, a.confirmation_timeout_seconds, start=True, now=moment, repeat_seconds=self.settings['repeat_seconds'])
                if reminders:
                    a.reminder_text = '\n'.join(reminders)
                    a._speak(' '.join(reminders))
        a._refresh_schedule()
        self.delivery.process(a.log_path, self.settings)
        events, notices = read_history(self.folder)
        from .history_display import display_event
        events = [display_event(e) for e in events]
        rows = ''.join('<tr>'+''.join('<td style="padding:8px;border:1px solid #ddd">'+html.escape(str(e.get(key,'')))+'</td>' for key in ('date','scheduled_time','name','strength','status','display_updated','display_reason'))+'</tr>' for e in events)
        mails = ''.join('<p><b>Family notification</b><br>To: '+html.escape(n.get('recipient') or 'No recipient saved')+'<br>'+html.escape(n.get('subject', n['type']))+'<br>'+html.escape(n['message'])+'<br>Delivery: '+html.escape(n.get('delivery_status', 'not_sent').replace('_', ' '))+'</p>' for n in notices)
        self.history.value = '<p>Self-reported records; Unconfirmed does not establish a missed dose.</p><table><tr><th>Date</th><th>Time</th><th>Medication</th><th>Strength</th><th>Status</th><th>Updated</th><th>Reason</th></tr>'+rows+'</table>'+(mails or '<p>No family notifications yet.</p>')

    async def _run(self):
        while not self.closed:
            await asyncio.sleep(1)
            try:
                self.tick()
            except Exception:
                self.message.value = 'Could not refresh records. Check the saved files and select Refresh history.'

    def close(self):
        self.closed = True
        if self.task:
            self.task.cancel()
        self.app.unobserve(self._apply_settings, names='simulation_text')
        self.app.close()
        for widget in (self.clock,self.automatic,self.reminders,self.timeout,self.email,self.message,self.history,self.time_selector,self.widget):
            widget.close()
