from collections import deque
import ast
import re
from custom_exceptions import *
from typing import Union, Optional
import sys
import os


def init(tree, glbs, white_listed, variable_assigns, lines):
    queue = deque([])
    for comp in tree.body:
        if not isinstance(comp, (ast.Import, ast.ImportFrom, ast.alias, ast.Expr)):
            if isinstance(comp, (ast.If, ast.For, ast.While)):
                if_queue = deque([comp])
                cond_assignments = []
                if_count = 0
                if_set = set()
                while if_queue:
                    stmt = if_queue.popleft()
                    # dgat about checking if the if-statement makes a constant everywhere neatly.
                    if isinstance(stmt, ast.If):
                        if_count += 1
                        for n in stmt.body + stmt.orelse:
                            if_queue.append(n)
                    elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                        cond_assignments.append(stmt)
                    elif isinstance(stmt, (ast.For, ast.While)):
                        for node in stmt.body + stmt.orelse:
                            if_queue.append(node)
                    # elif isinstance(stmt, ast.FunctionDef, ast.ClassDef): # not used bc idc about function/class constants rn.
                for c_ass in cond_assignments:
                    glbs.append(c_ass)
                    t_queue = deque(c_ass.targets)
                    while t_queue:
                        node = t_queue.popleft()
                        if isinstance(node, ast.Tuple):
                            for n in node.elts:
                                t_queue.append(n)
                        elif isinstance(node, ast.Name):
                            if_set.add(node.id)
                            a, b = white_listed.get(node.id, (0, 0))
                            # only whitelist the first if-statement's constant assignments
                            if b == 0:
                                white_listed[node.id] = a + 1, b
                for id in if_set:
                    a, b = white_listed[id]
                    white_listed[id] = a, b + 1
            else:
                glbs.append(comp)
                queue.append(comp)
    while queue:
        comp = queue.popleft()
        if isinstance(comp, (ast.Assign, ast.AnnAssign)):
            variable_assigns.append(comp)
        elif isinstance(comp, (ast.FunctionDef, ast.ClassDef)):
            for bd in comp.body:
                queue.append(bd)
        elif isinstance(comp, (ast.If, ast.For, ast.While)):
            for bd in comp.body + comp.orelse:
                queue.append(bd)
            if isinstance(comp, ast.For) and not re.fullmatch("[a-z]_", comp.target.id):
                raise SnakeCaseConventionError(f"for loop's target ({comp.target.id}) should be in snake_case.\n" + print_line_info(comp, lines))


def print_line_info(occ: Union[ast.AST], lines: list[str]) -> str:
    res = f"Line: {occ.lineno} - {occ.end_lineno}; Col: {occ.col_offset} - {occ.end_col_offset};\n"
    res += '\n'.join(lines[occ.lineno - 1:occ.end_lineno])
    return res


def flat_grab_names(vars: list) -> list:
    result = []
    for var in vars:
        if isinstance(var, ast.Assign):
            for t in var.targets:
                if isinstance(t, ast.Tuple):
                    tup_unpack_queue = deque([t])
                    while tup_unpack_queue:
                        node = tup_unpack_queue.popleft()
                        if isinstance(node, ast.Tuple):
                            for item in node.elts:
                                tup_unpack_queue.append(item)
                        else:  # isinstance(node, ast.Assign)
                            result.append(node)
                else:
                    result.append(t)
        elif isinstance(var, ast.AnnAssign):
            result.append(var.target)
    return result


def check_constants_overwrite(glbs, white_listed, lines):
    global_var_names = flat_grab_names(glbs)

    constants = re.compile("[A-Z_]+")

    hashed_global_var_names = {}
    for n in global_var_names:
        hashed_global_var_names.setdefault(n.id, []).append(n)

    for name, occurences in hashed_global_var_names.items():
        print(len(occurences))
        if re.fullmatch(constants, name) and (white_listed.get(name, (1, 0))[1] > 1 or len(occurences) - white_listed.get(name, (1, 0))[0] > 0):
            raise ConstantConventionError(f"variable {name} is in UPPER_CASE_WITH_UNDERSCORES, yet it's assigned multiple times.\n" +
                                          '\n'.join(map(lambda x:print_line_info(x, lines), occurences)))


def uses(head: ast.AST, type_: type, attrs: Optional[dict[str, object]] = None) -> Optional[ast.AST]:
    if attrs is None:
        attrs = {}

    if isinstance(head, list):
        queue = deque(head)
    else:
        queue = deque([head])
    while queue:
        curr = queue.popleft()
        if isinstance(curr, type_):
            try:
                for k, v in attrs.items():
                    ks = k.split('.')
                    curry = curr
                    for at in ks:
                        curry = getattr(curry, at)
                    if curry != v:
                        break
            except AttributeError:
                continue
            else:
                return curr
        for att in vars(curr).values():
            if isinstance(att, ast.AST):
                queue.append(att)
            if isinstance(att, list):
                for n in att:
                    queue.append(n)
    return None


def check_cases(tree, lines):
    _opens_wth, _opens = 0, 0
    fun_names = set()
    var_names = set()
    class_names = set()
    queue = deque(tree.body)

    opened_files = set()
    used_files = set()
    while queue:
        stmt = queue.popleft()
        # dgat about checking if the if-statement makes a constant everywhere neatly.
        if isinstance(stmt, ast.If):
            if isinstance(stmt.test, ast.Compare):
                if isinstance(stmt.test.left, ast.Constant):
                    if isinstance(stmt.test.comparators[0], ast.Constant):
                        ComparisonConventionError(f"Calculate the constant comparison before hand. It's always going to be {eval(ast.unparse(stmt.test))}!\n" +
                                                  print_line_info(stmt, lines)).trigger()
                    else:
                        ComparisonConventionError("Put constants on the right side when comparing!\n" + print_line_info(stmt, lines)).trigger()
                else:
                    if isinstance(stmt.test.comparators[0].value, bool) and isinstance(stmt.test.ops[0], (ast.IsNot, ast.Is, ast.NotEq, ast.Eq)):
                        r = stmt.test.comparators[0].value
                        if isinstance(stmt.test.ops[0], (ast.IsNot, ast.NotEq)):
                            r = not r
                        if r:
                            ComparisonConventionError(f"Just use if {ast.unparse(stmt.test.left)}! "
                                                      f"No need to do "
                                                      f"True == "
                                                      f"True, etc.\n" + print_line_info(stmt, lines)).trigger()
                        else:
                            ComparisonConventionError(f"Just use if not {ast.unparse(stmt.test.left)}! "
                                                      f"No need to do "
                                                      f"True == "
                                                      f"True, etc.\n" + print_line_info(stmt, lines)).trigger()
            elif isinstance(stmt.test, ast.Constant):
                if isinstance(stmt.test.value, bool):
                    if stmt.test.value:
                        TestConventionError(
                            "Always reachable. Get rid of the if-statement's test and unindent its body.\n" + print_line_info(stmt, lines)).trigger()
                    else:
                        TestConventionError(
                            "Never reachable. Get rid of the entire if-statement.\n"
                            + print_line_info(stmt, lines)).trigger()
                else:
                    TestConventionError(f"Calculate the bool cast of the costant beforehand. It's always going to be "
                                        f"{bool(stmt.test.value)}!\n" + print_line_info(stmt, lines)).trigger()
            for n in stmt.body + stmt.orelse:
                queue.append(n)
            queue.append(stmt.test)
        elif isinstance(stmt, ast.Assign):
            if uses(stmt.value, ast.Lambda):
                LambdaDenonymizedConventionError(
                    "Assignment eliminates the sole benefit a lambda can offer over an explicit def\n" + print_line_info(stmt, lines)).trigger()
            for t in stmt.targets:
                queue.append(t)
            if isinstance(stmt.value, ast.Tuple):
                for v in stmt.value.elts:
                    queue.append(v)
            else:
                queue.append(stmt.value)
            if curr := uses(stmt.value, ast.Call, attrs={'func.id': 'open'}):
                LightOutDatedConventionError(f"Just use with-as.\nwith open(file_path) as {curr.func.id}: ...\n" + print_line_info(stmt, lines)).trigger()
        elif isinstance(stmt, ast.NamedExpr):
            if uses(stmt.value, ast.Lambda):
                LambdaDenonymizedConventionError(
                    "Assignment eliminates the sole benefit a lambda can offer over an explicit def\n" + print_line_info(stmt, lines)).trigger()
            var_names.add(stmt.target)
            queue.append(stmt.value)
        elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
            if uses(stmt.value, ast.Lambda):
                LambdaDenonymizedConventionError(
                    "Assignment eliminates the sole benefit a lambda can offer over an explicit def\n" + print_line_info(stmt, lines)).trigger()
            var_names.add(stmt.target)
            queue.append(stmt.value)
        elif isinstance(stmt, (ast.For, ast.While)):
            if isinstance(stmt.test, ast.Compare):
                if isinstance(stmt.test.left, ast.Constant):
                    if isinstance(stmt.test.comparators[0], ast.Constant):
                        ComparisonConventionError(f"Calculate the constant comparison before hand. It's always going to be {eval(ast.unparse(stmt.test))}!\n" +
                                                  print_line_info(stmt, lines)).trigger()
                    else:
                        ComparisonConventionError("Put constants on the right side when comparing!\n" + print_line_info(stmt, lines)).trigger()
                else:
                    if isinstance(stmt.test.comparators[0].value, bool) and isinstance(stmt.test.ops[0], (ast.IsNot, ast.Is, ast.NotEq, ast.Eq)):
                        r = stmt.test.comparators[0].value
                        if isinstance(stmt.test.ops[0], (ast.IsNot, ast.NotEq)):
                            r = not r
                        if r:
                            ComparisonConventionError(f"Just use if {ast.unparse(stmt.test.left)}! "
                                                      f"No need to do "
                                                      f"True == "
                                                      f"True, etc.\n" + print_line_info(stmt, lines)).trigger()
                        else:
                            ComparisonConventionError(f"Just use if not {ast.unparse(stmt.test.left)}! "
                                                      f"No need to do "
                                                      f"True == "
                                                      f"True, etc.\n" + print_line_info(stmt, lines)).trigger()
            elif isinstance(stmt.test, ast.Constant):
                if isinstance(stmt.test.value, bool):
                    if stmt.test.value:
                        if not uses(stmt.body, ast.Break):
                            TestConventionError("Infinite loop. Introduce a testing condition besides True or use a break somewhere.\n" + print_line_info(
                                stmt, lines)).trigger()
                    else:
                        TestConventionError(
                            "Never reachable. Get rid of the entire while-loop.\n"
                            + print_line_info(stmt, lines)).trigger()
                else:
                    TestConventionError(f"Calculate the bool cast of the costant beforehand. It's always going to be "
                                        f"{bool(stmt.test.value)}!\n" + print_line_info(stmt, lines)).trigger()
            for node in stmt.body + stmt.orelse:
                queue.append(node)
        elif isinstance(stmt, ast.UnaryOp):
            if isinstance(stmt.op, ast.Not) and isinstance(stmt.operand, ast.Compare) and isinstance(stmt.operand.ops[0], ast.Is):
                IsNotConventionError("`is not` is storngly preferred over `not is`. Only reason to use `not is` is when `not` covers "
                                     "not just an `is`\n" + print_line_info(stmt, lines)).trigger()
            queue.append(stmt.operand)
        elif isinstance(stmt, ast.BinOp):
            queue.append(stmt.left)
            queue.append(stmt.right)
        elif isinstance(stmt, ast.BoolOp):
            for val in stmt.values:
                queue.append(val)
        elif isinstance(stmt, ast.Expr):
            queue.append(stmt.value)
        elif isinstance(stmt, ast.Compare):
            if isinstance(stmt.comparators[0], ast.Constant) and stmt.comparators[0].value is None:
                if isinstance(stmt.ops[0], (ast.Eq, ast.NotEq)):
                    SingletonIsEqConventionError("Comparisons to singletons like None should always be done with is or is not, never the equality "
                                                 "operators\n" + print_line_info(stmt, lines)).trigger()
            elif isinstance(stmt.left, ast.Constant) and stmt.left.value is None:
                SingletonIsEqConventionError("Comparisons to singletons like None should have the singleton on the right side, not the left.\n" +
                                             print_line_info(stmt, lines)).trigger()
            if isinstance(stmt.left, ast.Call) and stmt.left.func.id == 'type':
                if isinstance(stmt.ops[0], (ast.Eq, ast.NotEq)):
                    SingletonIsEqConventionError("type is, not type ==\n" + print_line_info(stmt, lines)).trigger()
                if isinstance(stmt.ops[0], (ast.Is, ast.IsNot)):
                    if isinstance(stmt.comparators[0], ast.Call):
                        TypeInheritanceConventionError(
                            f"subclass({ast.unparse(stmt.left.args[0])}, {ast.unparse(stmt.comparators[0])}) is preferred over type({ast.unparse(stmt.left.args[0])}) is "
                            f"type({ast.unparse(stmt.comparators[0])})\n"
                            f"If you worry about inheritance, you most likely didn't use OOP properly.\n" + print_line_info(
                                stmt, lines)).trigger()
                    else:
                        TypeInheritanceConventionError(f"isinstance({ast.unparse(stmt.left.args[0])}, {ast.unparse(stmt.comparators[0])}) is preferred over "
                                                       f"type ({ast.unparse(stmt.left.args[0])}) is "
                                                       f"{ast.unparse(stmt.comparators[0])}\n"
                                                       f"If you worry about inheritance, you most likely didn't use OOP properly.\n" + print_line_info(
                            stmt, lines)).trigger()
            elif isinstance(stmt.comparators[0], ast.Call) and stmt.comparators[0].func.id == 'type':
                if isinstance(stmt.ops[0], (ast.Eq, ast.NotEq)):
                    SingletonIsEqConventionError("type is, not type ==\n" + print_line_info(stmt, lines)).trigger()
                SingletonIsEqConventionError("Comparisons of type should have the first type call on the left." + print_line_info(stmt, lines)).trigger()

            queue.append(stmt.left)
            for val in stmt.comparators:
                queue.append(val)
        elif isinstance(stmt, ast.Call):
            for a in stmt.args + stmt.keywords + [stmt.func]:
                queue.append(a)

            try:
                if stmt.func.id == 'open':
                    _opens += 1
                    if _opens > _opens_wth:
                        LightOutDatedConventionError("There are opens not controlled by a with-as statement." + print_line_info(stmt, lines)).trigger()
            except AttributeError:
                pass
        elif isinstance(stmt, (ast.Starred, ast.keyword)):
            queue.append(stmt.value)
        elif isinstance(stmt, (ast.Tuple,)):
            for item in stmt.elts:
                queue.append(item)
        elif isinstance(stmt, ast.IfExp):
            queue.append(stmt.test)
            queue.append(stmt.body)
            queue.append(stmt.orelse)
        elif isinstance(stmt, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            queue.append(stmt.elt)
            for com in stmt.generators:
                queue.append(com)
        elif isinstance(stmt, ast.DictComp):
            queue.append(stmt.key)
            queue.append(stmt.value)
            for com in stmt.generators:
                queue.append(com)
        elif isinstance(stmt, ast.comprehension):
            queue.append(stmt.target)
            queue.append(stmt.iter)
        elif isinstance(stmt, ast.Try):
            for b in stmt.body + stmt.orelse + stmt.finalbody:
                queue.append(b)
            for h in stmt.handlers:
                queue.append(h.body)
        elif isinstance(stmt, ast.With):
            for item in stmt.items:
                if isinstance(item.context_expr, ast.Call) and item.context_expr.func.id == 'open':
                    _opens_wth += 1
                queue.append(item.context_expr)
                queue.append(item.optional_vars)
                for b in stmt.body:
                    queue.append(b)
        elif isinstance(stmt, ast.Attribute):
            print(stmt.attr)
            dunder_map = {"__dict__": "vars"}
            for nm in ('len', 'repr', 'str', 'bool'):
                dunder_map[f"__{nm}__"] = nm

            BuiltInsInsteadOfDunderConventionError(
                f"{ast.unparse(stmt.value)}.{stmt.attr} should be {dunder_map[stmt.attr]}({ast.unparse(stmt.value)})\n" + print_line_info(
                    stmt, lines)).trigger()



        elif isinstance(stmt, ast.Lambda):
            pass
        elif isinstance(stmt, ast.FunctionDef):
            fun_names.add(stmt)
            for b in stmt.body:
                queue.append(b)

            func_q = deque(stmt.body)
            blanks, non_blanks = [], []
            blanks_valid = True
            while func_q:
                fun_c = func_q.popleft()
                if isinstance(fun_c, ast.Return):
                    if fun_c.value is None:
                        blanks.append(fun_c)
                    else:
                        non_blanks.append(fun_c)
                        blanks_valid = False
                elif isinstance(fun_c, list):
                    for n in fun_c:
                        func_q.append(n)
                else:
                    try:
                        for n in vars(fun_c).values():
                            func_q.append(n)
                    except TypeError:
                        pass
                # print(func_q)

            blanks = [ast.unparse(blank) for blank in blanks]
            non_blanks = [ast.unparse(unb) for unb in non_blanks]
            if not blanks_valid and blanks:
                BlankReturnConventionError("Either all return statements in a function should return an expression, or none of them should.\n"
                                           + f"{blanks=}; {non_blanks=};\n"
                                           + print_line_info(stmt, lines)).trigger()
        elif isinstance(stmt, ast.ClassDef):
            class_names.add(stmt)
            for b in stmt.body:
                if isinstance(b, ast.FunctionDef):
                    arguments_obj = b.args
                    decos = []
                    for deco in b.decorator_list:
                        try:
                            decos.append(deco.id)
                        except AttributeError:
                            pass
                    if any(map(lambda x: x.arg in ("cls", "self"), arguments_obj.kwonlyargs)):
                        MethodConventionError(f"Don't use kwargs for cls and self...").trigger()
                    elif "staticmethod" not in decos:
                        if len(arguments_obj.args) == 0 or arguments_obj.args[0].arg not in ('cls', 'self'):
                            MethodConventionError(f"Insert @staticmethod at line {stmt.lineno}\nIf you wanted a classmethod or an instance "
                                                  f"method, use cls or self respectively.").trigger()
                    elif arguments_obj.args[0].arg == "cls":
                        if "classmethod" not in decos:
                            MethodConventionError(
                                f"Class methods' arg list should start with `cls`\n" + print_line_info(arguments_obj.args[0], lines)).trigger()
                    elif arguments_obj.args[0].arg != "cls" and arguments_obj.args[0].arg != "self":
                        MethodConventionError(
                            f"Instance methods' arg list should start with `self`\n" + print_line_info(arguments_obj.args[0], lines)).trigger()
                queue.append(b)


    for v_n in var_names:
        if not re.fullmatch("[a-z_]+|[A-Z_]+", v_n.id):
            SnakeCaseConventionError(f"variable {v_n.id} is not in snake_case nor a const\n" + print_line_info(v_n, lines)).trigger()
    for f_n in fun_names:
        if not re.fullmatch("[a-z_]+", f_n.name):
            SnakeCaseConventionError(f"function {f_n.name} is not in snake_case nor a const\n" + print_line_info(f_n, lines)).trigger()
        ar = f_n.args
        for a in ar.posonlyargs + ar.args + ar.kwonlyargs + [ar.vararg, ar.kwarg]:
            if a is not None and not re.fullmatch("[a-z_]+", a.arg):
                SnakeCaseConventionError(f"function argument {a.arg} is not in snake_case\n" + print_line_info(f_n, lines)).trigger()
    for c_n in class_names:
        if not re.fullmatch("[A-Z]+", c_n.name):
            CapitalWordsConventionError(f"class {c_n.name} is not in CapWords\n" + print_line_info(c_n, lines)).trigger()


def scan(fp: str) -> None:
    with open(fp, mode='r') as f:
        source_code = f.read()

    variable_assigns = deque([])
    tree = ast.parse(source_code, mode='exec')

    glbs, white_listed = [], {}
    lines = source_code.splitlines()
    init(tree, glbs, white_listed, variable_assigns, lines)
    check_constants_overwrite(glbs, white_listed, lines)
    check_cases(tree, lines)


def main():
    args = sys.argv
    if len(args) not in (1, 2):
        print("Usage: python style51.py filepath?")

    if len(args) == 1:
        _, _, filenames = next(os.walk(os.getcwd()), (None, None, []))
        filenames = [fn for fn in filenames if fn.endswith('.py')]
    else:
        filenames = [sys.argv[1]]

    for file_path in filenames:
        scan(file_path)


if __name__ == '__main__':
    main()
