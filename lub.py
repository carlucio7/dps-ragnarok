# -*- coding: utf-8 -*-
"""Leitor das tabelas .lub do cliente do Ragnarok (Lua 5.1 compilado).

Não executa nada do jogo: interpreta só as instruções que montam tabelas (constantes,
NEWTABLE, SETTABLE, SETLIST, GETGLOBAL/SETGLOBAL, MOVE...). Nomes globais que o arquivo
usa sem definir (ex.: SKID.NV_BASIC) viram símbolos ("SKID", "NV_BASIC"). Funções definidas
no arquivo são ignoradas.
"""

import struct


class Symbol(tuple):
    """Referência a um global que o arquivo não define (ex.: SKID.NV_BASIC = Symbol(("SKID", "NV_BASIC")))."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple.__getitem__(self, key)
        return Symbol(tuple(self) + (key,))


class _Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0
        if data[:4] != b"\x1bLua" or data[4] != 0x51:
            raise ValueError("não é Lua 5.1 compilado")
        self.int_size, self.size_t, self.instr, self.num_size = data[7], data[8], data[9], data[10]
        self.p = 12

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def int(self):
        v = int.from_bytes(self.d[self.p:self.p + self.int_size], "little", signed=True)
        self.p += self.int_size
        return v

    def string(self):
        n = int.from_bytes(self.d[self.p:self.p + self.size_t], "little")
        self.p += self.size_t
        s = self.d[self.p:self.p + n - 1] if n else None
        self.p += n
        return s

    def function(self):
        f = {}
        self.string()                          # nome do arquivo de origem
        self.int(), self.int()
        self.p += 4                             # upvalues, parâmetros, vararg, pilha
        n = self.int()
        f["code"] = struct.unpack_from("<%dI" % n, self.d, self.p)
        self.p += 4 * n
        consts = []
        for _ in range(self.int()):
            t = self.u8()
            if t == 0:
                consts.append(None)
            elif t == 1:
                consts.append(bool(self.u8()))
            elif t == 3:
                consts.append(struct.unpack_from("<d", self.d, self.p)[0])
                self.p += self.num_size
            elif t == 4:
                consts.append(self.string())
            else:
                raise ValueError("constante de tipo %d" % t)
        f["k"] = consts
        f["protos"] = [self.function() for _ in range(self.int())]
        self.p += self.int_size * self.int()            # linhas
        for _ in range(self.int()):                     # variáveis locais
            self.string()
            self.int(), self.int()
        for _ in range(self.int()):                     # nomes de upvalues
            self.string()
        return f


def _key(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def run(data, encoding="utf-8"):
    """Executa o trecho principal e devolve os globais definidos {nome: valor}."""
    f = _Reader(data).function()
    k = [(_key(c) if not isinstance(c, bytes) else _text(c, encoding)) for c in f["k"]]
    code = f["code"]
    reg = {}
    env = {}

    def rk(x):
        return k[x & 0xFF] if x & 0x100 else reg.get(x)

    def get(table, key):
        if isinstance(table, Symbol):
            return table[key]
        if isinstance(table, dict):
            return table.get(_key(key))
        return None

    pc = 0
    while pc < len(code):
        i = code[pc]
        pc += 1
        op, a = i & 0x3F, (i >> 6) & 0xFF
        c, b = (i >> 14) & 0x1FF, (i >> 23) & 0x1FF
        bx = (i >> 14) & 0x3FFFF
        if op == 0:                                     # MOVE
            reg[a] = reg.get(b)
        elif op == 1:                                   # LOADK
            reg[a] = k[bx]
        elif op == 2:                                   # LOADBOOL
            reg[a] = bool(b)
            if c:
                pc += 1
        elif op == 3:                                   # LOADNIL
            for r in range(a, b + 1):
                reg[r] = None
        elif op == 5:                                   # GETGLOBAL
            name = k[bx]
            reg[a] = env[name] if name in env else Symbol((name,))
        elif op == 6:                                   # GETTABLE
            reg[a] = get(reg.get(b), rk(c))
        elif op == 7:                                   # SETGLOBAL
            env[k[bx]] = reg.get(a)
        elif op == 9:                                   # SETTABLE
            t = reg.get(a)
            if isinstance(t, dict):
                t[_key(rk(b))] = rk(c)
        elif op == 10:                                  # NEWTABLE
            reg[a] = {}
        elif op in (12, 13, 14, 15):                    # ADD SUB MUL DIV (números)
            x, y = rk(b), rk(c)
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                reg[a] = _key([x + y, x - y, x * y, x / y if y else 0][op - 12])
            else:
                reg[a] = None
        elif op == 18:                                  # UNM
            v = reg.get(b)
            reg[a] = -v if isinstance(v, (int, float)) else None
        elif op == 21:                                  # CONCAT
            parts = [reg.get(r) for r in range(b, c + 1)]
            reg[a] = "".join(str(p) for p in parts) if all(isinstance(p, (str, int, float)) for p in parts) else None
        elif op == 34:                                  # SETLIST
            if c == 0:
                c = code[pc]
                pc += 1
            t = reg.get(a)
            if isinstance(t, dict) and b:
                for j in range(1, b + 1):
                    t[(c - 1) * 50 + j] = reg.get(a + j)
        elif op == 36:                                  # CLOSURE (funções do arquivo: ignoradas)
            reg[a] = None
        elif op == 30:                                  # RETURN
            break
        # o resto (laços, chamadas) não aparece nas tabelas de dados
    return env


def _text(raw, encoding):
    for enc in (encoding, "utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")
