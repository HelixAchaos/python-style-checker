print('hello world')

def foo():
    pass


F = True
F = False
if F == True:
    pass

class A:
    @staticmethod
    def Foo(cls, hey):
        pass

while True:
    pass
# result:
"""
print('hello world')

def foo():
    pass

F = True
if F:
    pass

class A:
    @classmethod
    def foo(cls, hey):
        pass
"""
