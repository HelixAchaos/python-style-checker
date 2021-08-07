
import json
with open('error_white_list.json', mode='r') as f:
    options = json.load(f)

class SoftError(Exception):
    def __init__(self, msg: str = "") -> None:
        self.msg = msg

    @property
    def msg(self) -> str:
        return self.args[0]

    @msg.setter
    def msg(self, msg) -> None:
        self.args = (msg,)

    def trigger(self):
        if options['Exception']:
            return
        if not options[self.__class__.__name__] and not any(options[parent.__name__] for parent in self.__class__.__bases__):
            raise self

class ConstantConventionError(SoftError):
    pass

class SnakeCaseConventionError(SoftError):
    pass

class CapitalWordsConventionError(SoftError):
    pass

class MethodConventionError(SoftError):
    pass

class SingletonIsEqConventionError(SoftError):
    pass

class IsNotConventionError(SoftError):
    pass


class LambdaDenonymizedConventionError(SoftError):
    pass


class RedundantConventionError(SoftError):
    pass


class LightOutDatedConventionError(SoftError):
    pass


class BuiltInsInsteadOfDunderConventionError(SoftError):
    pass


class BlankReturnConventionError(SoftError):
    pass


class TypeInheritanceConventionError(SoftError):
    pass


class ComparisonConventionError(SoftError):
    pass


class TestConventionError(SoftError):
    pass
