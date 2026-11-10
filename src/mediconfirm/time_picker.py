"""Choose one or more daily intake times without typing separators."""
import ipywidgets as w
import traitlets


class IntakeTimes(w.VBox):
    value = traitlets.Unicode('08:00')

    def __init__(self, value='08:00', **kwargs):
        self._syncing = False
        self._pairs = []
        self.rows = w.VBox()
        self.add = w.Button(description='+ Add intake time')
        self.add.on_click(lambda _: self._add('08:00'))
        super().__init__([self.rows, self.add], **kwargs)
        self.observe(self._load_value, names='value')
        self.value = value
        if not self._pairs:
            self._load_value({'new': value})

    def _load_value(self, change):
        if self._syncing:
            return
        # Keep invalid programmatic values for the form validator to reject.
        values = change['new'].split(';') if change['new'] else []
        if any(len(t)!=5 or t[2]!=':' or not t[:2].isdigit() or not t[3:].isdigit() or int(t[:2])>23 or int(t[3:])>59 for t in values):
            return
        for pair in self._pairs:
            for item in pair['box'].children:
                item.close()
            pair['box'].close()
        self._pairs = []
        self._syncing = True
        for value in values:
            self._add(value)
        self._syncing = False
        self.rows.children = tuple(p['box'] for p in self._pairs)

    def _add(self, value):
        hour, minute = value.split(':')
        h = w.Select(options=[f'{v:02}' for v in range(24)], value=hour, rows=3, layout=w.Layout(width='65px'))
        m = w.Select(options=[f'{v:02}' for v in range(60)], value=minute, rows=3, layout=w.Layout(width='65px'))
        remove = w.Button(description='Remove time', layout=w.Layout(width='110px'))
        box = w.HBox([h,w.Label(':'),m,remove])
        pair = dict(hour=h,minute=m,box=box)
        self._pairs.append(pair)
        def refresh(change=None):
            if self._syncing:
                return
            self._syncing = True
            self.value = ';'.join(p['hour'].value+':'+p['minute'].value for p in self._pairs)
            self._syncing = False
        h.observe(refresh,names='value');m.observe(refresh,names='value')
        def delete(_):
            self._pairs.remove(pair)
            self.rows.children=tuple(p['box'] for p in self._pairs)
            for item in box.children:item.close()
            box.close();refresh()
        remove.on_click(delete)
        self.rows.children=tuple(p['box'] for p in self._pairs)
        refresh()

    def close(self):
        for pair in self._pairs:
            for item in pair['box'].children:
                item.close()
            pair['box'].close()
        self.rows.close()
        self.add.close()
        super().close()
