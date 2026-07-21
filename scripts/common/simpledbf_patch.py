"""Monkey patch para `simpledbf.Dbf5`.

Corrige erro de parse com datas zeradas (00000000) encapsulando `datetime.date` no try/except.
Issue original sem resolução: github.com/rnelsonchem/simpledbf/issues/10

Importe este módulo antes de instanciar `Dbf5`.
"""
import struct
import datetime
from simpledbf import Dbf5


def _get_recs_corrigido(self, chunk=None):
    if chunk is None:
        chunk = self.numrec

    for i in range(chunk):
        record = struct.unpack(self.fmt, self.f.read(self.fmtsiz))
        if record[0] != b' ':
            continue

        self._dtypes = {}
        result = []
        for idx, value in enumerate(record):
            name, typ, size = self.fields[idx]
            if name == 'DeletionFlag':
                continue

            if typ == "C":
                if name not in self._dtypes:
                    self._dtypes[name] = "str"
                value = value.strip()
                if value == b'':
                    value = self._na
                else:
                    value = value.decode(self._enc)
                    if self._esc:
                        value = value.replace('"', self._esc + '"')

            elif typ == "N":
                if b'.' in value:
                    if name not in self._dtypes:
                        self._dtypes[name] = "float"
                    value = float(value)
                else:
                    try:
                        value = int(value)
                        if name not in self._dtypes:
                            self._dtypes[name] = "int"
                    except Exception:
                        value = float('nan')

            elif typ == 'D':

                try:
                    y, m, d = int(value[:4]), int(value[4:6]), int(value[6:8])
                    value = datetime.date(y, m, d)
                    if name not in self._dtypes:
                        self._dtypes[name] = "date"
                except Exception:
                    value = self._na

            elif typ == 'L':
                if name not in self._dtypes:
                    self._dtypes[name] = "bool"
                if value in b'TyTt':
                    value = True
                elif value in b'NnFf':
                    value = False
                else:
                    value = self._na

            elif typ == 'F':
                if name not in self._dtypes:
                    self._dtypes[name] = "float"
                try:
                    value = float(value)
                except Exception:
                    value = float('nan')

            else:
                raise ValueError(f'Column type "{value}" not yet supported.')

            result.append(value)
        yield result


Dbf5._get_recs = _get_recs_corrigido