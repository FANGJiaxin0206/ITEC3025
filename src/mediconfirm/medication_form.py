"""App-style medication form: add rows, edit fields, save one whole list."""
import html
from collections import OrderedDict
from pathlib import Path
import ipywidgets as w
from .time_picker import IntakeTimes
from .bulk_medications import load_saved_medications, save_medication_entries

class MedicationListForm:

    def __init__(self, path):
        self.path = Path(path)
        self.medications = []
        self.rows = []
        self._listeners = []
        self._closed = False
        self.entries_box = w.VBox()
        self.message = w.HTML()
        self.preview = w.HTML()
        self.add_button = w.Button(description='+ Add medication', layout=w.Layout(width='150px'))
        self.save_button = w.Button(description='Save medication list', button_style='success', layout=w.Layout(width='160px'))
        self.add_button.on_click(lambda _: self.add_row())
        self.save_button.on_click(lambda _: self.save())
        self.widget = w.VBox([w.HTML('<h3>Medication list</h3><p>Complete the fields, add more rows if needed, then save the list. Use 100 mg for strength, 1 tablet for dose, and the hour/minute selectors for intake times.</p>'), self.entries_box, w.HBox([self.add_button, self.save_button]), self.message, self.preview])
        try:
            self.medications = load_saved_medications(self.path)
        except Exception as exc:
            self.message.value = '<b>Could not load: </b>' + html.escape(str(exc)) + ' The original file was not changed.'
        groups = OrderedDict()
        for med in self.medications:
            key = (med['name'], med['strength'], med['dose'])
            groups.setdefault(key, []).append(med['time'])
        for (name, strength, dose), times in groups.items():
            self.add_row({'name': name, 'strength': strength, 'dose': dose, 'time': ';'.join(times)}, dirty=False)
        if not self.rows:
            self.add_row(dirty=False)
        elif self.medications:
            self.message.value = 'Your saved medication list is ready. You can edit it and save again.'
        self._show_preview()

    def on_saved(self, callback):
        self._listeners.append(callback)

        def unsubscribe():
            if callback in self._listeners:
                self._listeners.remove(callback)
        return unsubscribe

    def mark_dirty(self, change=None):
        self.message.value = 'You have unsaved changes. Select Save medication list when ready; checks use the last saved list.'

    def add_row(self, initial=None, dirty=True):
        values = initial or {}
        fields = {}
        labels = [('name', 'Medication name', 'As printed on the package'), ('time', 'Schedule time', '08:00 or 08:00;20:00'), ('strength', 'Strength', 'e.g. 100 mg'), ('dose', 'Dose per intake', 'e.g. 1 tablet')]
        boxes = []
        for key, title, placeholder in labels:
            field = IntakeTimes(value=values.get(key, '08:00')) if key == 'time' else w.Text(value=values.get(key, ''), placeholder=placeholder, layout=w.Layout(width='100%'), continuous_update=True)
            field.observe(self.mark_dirty, names='value')
            fields[key] = field
            boxes.append(w.VBox([w.Label(title), field], layout=w.Layout(width='300px' if key == 'time' else '210px')))
        delete = w.Button(description='Remove', button_style='', layout=w.Layout(width='70px'))
        box = w.Box(boxes + [delete], layout=w.Layout(display='flex', flex_flow='row wrap', align_items='flex-end', border='1px solid #ddd', padding='10px', margin='4px 0'))
        row = {'fields': fields, 'box': box, 'delete': delete, 'parts': boxes}
        delete.on_click(lambda _: self.remove_row(row))
        self.rows.append(row)
        self.entries_box.children = tuple((item['box'] for item in self.rows))
        if dirty:
            self.mark_dirty()
        return row

    def remove_row(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.entries_box.children = tuple((item['box'] for item in self.rows))
        self._close_row(row)
        if not self.rows:
            self.add_row(dirty=False)
        self.mark_dirty()

    def save(self):
        rows = [{key: field.value.strip() for key, field in row['fields'].items()} for row in self.rows]
        rows = [row for row in rows if any(row[key] for key in ('name', 'strength', 'dose')) or row['time'] not in ('', '08:00')]
        try:
            saved = save_medication_entries(rows, self.path)
        except Exception as exc:
            self.message.value = '<b>Could not save: </b>' + html.escape(str(exc)) + ' The saved medication list was not replaced.'
            return False
        self.medications = saved
        self.message.value = 'Medication list saved (' + str(len(saved)) + ' scheduled entries). It will load automatically next time.'
        self._show_preview()
        for callback in tuple(self._listeners):
            try:
                callback(saved)
            except Exception:
                self.message.value += ' The camera interface could not refresh. Rerun section 4; your list has been saved.'
        return True

    def _show_preview(self):
        if not self.medications:
            self.preview.value = ''
            return
        rows = ''.join(('<tr>' + ''.join(("<td style='border:1px solid #ccc;padding:8px'>" + html.escape(med[key]) + '</td>' for key in ('name', 'time', 'strength', 'dose'))) + '</tr>' for med in self.medications))
        self.preview.value = '<b>Saved medication list (used for verification)</b><table><tr><th>Medication name</th><th>Schedule time</th><th>Strength</th><th>Dose per intake</th></tr>' + rows + '</table>'

    def _close_row(self, row):
        for field in row['fields'].values():
            field.unobserve(self.mark_dirty, names='value')
            field.close()
        for box in row['parts']:
            for child in box.children:
                if isinstance(child, w.Label):
                    child.close()
            box.close()
        row['delete'].close()
        row['box'].close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._listeners.clear()
        for row in self.rows:
            self._close_row(row)
        for item in [self.entries_box, self.add_button, self.save_button, self.message, self.preview, self.widget]:
            item.close()
