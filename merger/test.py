# -*- encoding: utf-8 -*-
from __future__ import print_function

import sys
from copy import deepcopy
from collections import defaultdict
from itertools import chain, izip

import jsparser

def pairs(iterable):
  it = iter(iterable)
  e1 = next(it)

  for e2 in it:
    yield e1, e2
    e1 = e2

def childs(node):
  for a in BaseVisitor.CHILD_ATTRS:
    child = getattr(node, a, None)
    # a='value' может содержать не только узел.
    if child and isinstance(child, jsparser.Node):
      yield child, a
  for i, n in enumerate(node): yield n, i
jsparser.Node._childs = property(childs)

class GraphNode(object):
  def __init__(self, name):
    self.name = name
  def __str__(self):
    l = [x for x in dir(self) if x.startswith('g_')]
    if len(l):
      return '%s [%s]' % (self.name, ','.join(map(lambda x: '%s="%s"' % (x[2:], getattr(self, x)), l)))
    return self.name
  __repr__ = __str__

class BeginNode(GraphNode):
  def __init__(self):
    super(BeginNode, self).__init__('begin')
  g_shape = 'ellipse'
class EndNode(GraphNode):
  def __init__(self):
    super(EndNode, self).__init__('end')
  g_shape = 'ellipse'
class ConditionNode(GraphNode):
  def __init__(self, name):
    super(ConditionNode, self).__init__(name)
  g_shape = 'diamond'
class ActionNode(GraphNode):
  def __init__(self, name):
    super(ActionNode, self).__init__(name)
class GeneralRequestNode(ActionNode):
  def __init__(self, name):
    super(GeneralRequestNode, self).__init__(name)
  g_fillcolor = '#99CC33'
  g_style = 'filled'
class SubGraph(object):
  def __init__(self, name, parent=None):
    assert parent == None or isinstance(parent, SubGraph), type(parent)
    self.name = name
    self.nodes = [] # GraphNode
    self.subgraphs = [] # SubGraph
    self.__actions = [] # GraphNode | SubGraph
    self.parent = parent
    if parent:
      parent.subgraphs.append(self)
######################################
# Геттеры
######################################
  @property
  def entryPoint(self):
    return self.__actions[0]
  @property
  def endPoint(self):
    return self.__actions[-1]
  @property
  def edges(self):
    return pairs(self.__actions)
  def subgraph(self, name):
    sg = self
    while sg is not None:
      for g in sg.subgraphs:
        if g.name == name: return g
      sg = sg.parent
    raise Exception('No graph with name '+name)
  @property
  def _actions(self):
    return chain(self.__actions, (self.__endPoint,))
######################################
  def addAction(self, name):
    self._addNode(ActionNode(name))
  def addCall(self, g):
    self.__add(g)
  def _addNode(self, node):
    self.nodes.append(node)
    self.__add(node)
  def __add(self, endNode):
    # Выделяем первое действие в цепочке.
    if not len(self.__actions) and isinstance(endNode, ActionNode):
      endNode.g_style = 'filled'
      endNode.g_fillcolor = '#99CC33'
    self.__actions.append(endNode)

  def toDot(self, indent=0, out=sys.stdout):
    i = '  '*indent
    print('%s// Функция %s()'             % (i, self.name), file=out)
    print(self._header()                  % (i, self.name), file=out)
    print('%s  node [shape="rectangle"];' % i, file=out)
    print('%s  label="%s";'               % (i, self._label()), file=out)
    if len(self.nodes):
      print(file=out)
      for n in self.nodes:
        print('%s  %s;' % (i, n), file=out)

    print(file=out)
    for n1, n2 in self.edges:
      try:
        while isinstance(n1, SubGraph): n1 = n1.endPoint
        while isinstance(n2, SubGraph): n2 = n2.entryPoint
        print('%s  %s -> %s;' % (i, n1.name, n2.name), file=out)
      except IndexError: break
    if len(self.subgraphs):
      print(file=out)
      for g in self.subgraphs:
        g.toDot(indent+1, out)
    print('%s}' % i, file=out)
  def _header(self):
    return '%ssubgraph cluster%s {';
  def _label(self):
    return 'function %s()' % self.name
  # @property
  # def nodes(self):
    # for a in self.__actions:
      # if isinstance(a, GraphNode): yield a

class Graph(SubGraph):
  def __init__(self):
    super(Graph, self).__init__('Script')
    self._addNode(BeginNode())
    self.nodes.append(EndNode())
  def _header(self):
    return '%sdigraph %s {';
  def _label(self):
    return self.name

##########################################################################

class BaseVisitor(object):
  # value используется в RETURN
  CHILD_ATTRS = ['condition', 'thenPart', 'elsePart', 'expression', 'body', 'initializer', 'value']

  def __noop(self, node): pass

  def visit(self, node):
    # Получаем функцию вида visit_<тип_узла> у данного класса, которая
    # применяется к передаваемому узлу.
    call = lambda n: getattr(self, "visit_%s" % n.type, self.__noop)(n)
    r = call(node)
    if r: return r

    # Обходим все внутренние узлы с действиями
    for n,i in node._childs:
      if self.filter(n):
        r = self.visit(n)
        if r: return r
    
    call = lambda n: getattr(self, "after_visit_%s" % n.type, self.__noop)(n)
    return call(node)
  def filter(self, node):
    return True
  @staticmethod
  def _name(node):
    if node.type in ('IDENTIFIER', 'NUMBER'): return node.value
    if node.type == 'FUNCTION': return getattr(node, 'name', '<anonymous>')
    if node.type == 'CALL': return BaseVisitor._name(node[0])
    if node.type == 'DOT': return '.'.join((n.value for n in node))
    if node.type == 'STRING': return '"%s"' % node.value
    return ''
##########################################################################
# Печатает дерево узлов в компактном виде.
class PrintVisitor(BaseVisitor):
  def __init__(self, node=None):
    self.__indent = 0
    if node:
      self.visit(node)
  def visit(self, node):
    print('%s%s %s' % ('  '*self.__indent, node.type, self._name(node)))
    self.__indent += 1
    super(PrintVisitor, self).visit(node)
    self.__indent -= 1
# Добавляет всем узлам графа скрипта ссылку на родительский узел.
class AddParentVisitor(BaseVisitor):
  def __init__(self, node):
    super(AddParentVisitor, self).__init__()
    self.__current = None
    node._parent = None
    self.visit(node)
    self.addChangeHook()

  def visit(self, node):
    node._parent = self.__current
    self.__current = node
    super(AddParentVisitor, self).visit(node)
    self.__current = node._parent

  @staticmethod
  def addChangeHook():
    old__setattr__ = jsparser.Node.__setattr__
    def hook(self, name, obj):
      old__setattr__(self, name, obj)
      if name in BaseVisitor.CHILD_ATTRS and isinstance(obj, jsparser.Node):
        # print('%s.%s <= %s' % (getattr(self, 'type', None), name, getattr(obj, 'type', None)))
        old__setattr__(obj, '_parent', self)
    jsparser.Node.__setattr__ = hook
    # jsparser.Node.parent = property(lambda self: self._parent)
    def where(node):
      if not node._parent: return None
      try:
        return next(i for i, n in enumerate(node._parent) if n is node)
        # return node._parent.index(node)
      # except ValueError:
      except StopIteration:
        for attr in BaseVisitor.CHILD_ATTRS:
          child = getattr(node._parent, attr, None)
          if child is node:
            return attr
        raise ValueError()
    jsparser.Node._where = property(where)
    def removeNode(node, nodeForRemove):
      i = nodeForRemove._where
      if isinstance(i, int):
        del node[i]
      else:
        setattr(node, i, None)
    jsparser.Node._removeNode = removeNode
    jsparser.Node._neighbours = property(pairs)
    def equals(node1, node2):
      if node1 is node2: return True
      if node1 is None and node2 is not None: return False
      if node1.type != node2.type: return False
      if len(node1) != len(node2): return False
      name1 = getattr(node1, 'name', None)
      name2 = getattr(node2, 'name', None)
      if name1 != name2: return False
      name1 = getattr(node1, 'value', None)
      name2 = getattr(node2, 'value', None)
      if name1 != name2: return False
      # return node1 == node2

      for n1, n2 in izip(node1, node2):
        if not equals(n1, n2): return False
      return True
    jsparser.Node._equals = equals
    # jsparser.Node.__eq__ = equals
# Рефакторит AST для более удобного составления code-flow.
class RefactorVisitor(BaseVisitor):
  class Tokenizer(object):
    token = None
    lineno= -1

  def __init__(self, node):
    self.visit(node)
  def visit(self, node):
    self.__chainIf(node)
    super(RefactorVisitor, self).visit(node)
  def visit_IF(self, node):
    # Удаляет отрицание из условия.
    if node.condition.type == 'NOT':
      node.thenPart,node.elsePart = node.elsePart,node.thenPart
      node.condition = node.condition[0]# Условие под NOT
      node.condition._parent = node
      return self.visit_IF(node, part)
    elif node.condition.type == 'AND':
      self.__splitANDNode(node)
      return self.visit_IF(node, part)
    # elif node.condition.type == 'OR':
      # self.__splitORNode(node)
      # return self.visit_IF(node, part)
    elif node.condition.type == 'CALL':
      self.__popCALL(node)
      return self.visit_IF(node, part)
    elif node.condition.type == 'TRUE':
      self.__replaceNode(node._parent, node, node.thenPart)
      self.visit(node._parent)
      return True
    elif node.condition.type in ('FALSE', 'NULL'):
      self.__replaceNode(node._parent, node, node.elsePart)
      self.visit(node._parent)
      return True
  def visit_WHILE(self, node):
    if node.condition.type in ('NUMBER', 'TRUE', 'FALSE', 'NULL'):
      return

    node.body = self.__createNode('if',
      condition=node.condition,
      thenPart=node.body,
      elsePart=self.__createNode('break')
    )
    node.condition = self.__createNode('true')
  def visit_DO(self, node):
    if node.condition.type in ('NUMBER', 'TRUE', 'FALSE', 'NULL'):
      return
    node.body = self.__createNode('BLOCK',
      node.body,
      self.__createNode('if',
        condition=node.condition,
        thenPart =self.__createNode('break')
      )
    )
    node.condition = self.__createNode('true')

  def __splitANDNode(self, oldIf):
    """
# Пример рефакторинга
def test(x): # До
  if x>1 and x<3: print('then')
  else:           print('else')
def test(x): # После
  if x>1:    # oldIf
    if x<3: print('then')# newIf
    else:   print('else')
  else:
    print('else')

    """
    # Легче было бы создать внешний if, так как внутренний - это исходный
    # со второй частью условия. Но при этом невозможно протолкнуть изменения
    # вверх по дереву, поэтому создаем новый внутренний if.
    newIf = self.__createNode('if',
      condition= oldIf.condition[1],
      thenPart = oldIf.thenPart,
      elsePart = deepcopy(oldIf.elsePart)
    )
    # Корректируем внешний if
    oldIf.condition = oldIf.condition[0]
    oldIf.thenPart = newIf
  def __splitORNode(self, oldIf):
    """
# Пример рефакторинга
def test(x): # До
  if x<1 or x>3: print('then')
  else:          print('else')
def test(x): # После
  if x<1:   print('then')# oldIf
  else:
    if x>3: print('then')# newIf
    else:   print('else')

    """
    newIf = self.__createNode('if',
      condition = oldIf.condition[1],
      thenPart  = deepcopy(oldIf.thenPart),
      elsePart  = oldIf.elsePart
    )
    
    oldIf.condition = oldIf.condition[0]
    oldIf.elsePart = newIf
  def __popCALL(self, oldIf):
    """
# Пример рефакторинга
def test(f): # До
  if f(): print('then')
  else:   print('else')
def test(f): # После
  # Фиктивный if, т.к. менять можно только детей узла,
  # а у нас добавляется 1 узел на том же уровне.
  if True:# oldIf
    x = f()
    if x:   print('then')# newIf
    else:   print('else')

    """
    # Объявляем переменную и инициализируем ее условием
    var = self.__createNode('var',
      self.__createNode('IDENTIFIER', value='lastResult', initializer=oldIf.condition)
    )
    # Создаем новое условие, проверяющее указанную переменную
    newIf = self.__createNode('if',
      condition = self.__createNode('IDENTIFIER', value='lastResult'),
      thenPart  = oldIf.thenPart,
      elsePart  = oldIf.elsePart
    )
    # Меняем старое условие и прицепляем два созданных куска кода.
    oldIf.condition = self.__createNode('true')
    oldIf.thenPart  = self.__createNode('BLOCK', var, newIf)
    oldIf.elsePart  = None

  # Если подряд идут 2 if-а, причем у первого отсутствует часть else,
  # и они оба проверяют одну и ту же переменную на равенство, то второй
  # if можно прицепить к первому в часть else, если проверяемая переменная
  # не изменяется в теле первого if-а (здесь эта проверка не производится).
  def __chainIf(self, node):
    for n1, n2 in reversed(list(node._neighbours)):
      if n1.type == 'IF' and n2.type == 'IF':
        PrintVisitor(n1.condition)
        PrintVisitor(n2.condition)
        print(('---------------'))
        if n1.elsePart is None:
          c1 = n1.condition
          c2 = n2.condition
          if c1.type == 'EQ' and c2.type == 'EQ':
            # if c1[0]==c2[0] or c1[0]==c2[1] or c1[1]==c2[0] or c1[1]==c2[1]:
            if c1[0]._equals(c2[0]) or c1[0]._equals(c2[1]) or c1[1]._equals(c2[0]) or c1[1]._equals(c2[1]):
              n2._parent._removeNode(n2)
              n1.elsePart = n2

  @staticmethod
  def __replaceNode(node, oldNode, newNode):
    try:
      i = node.index(oldNode)
      node[i] = newNode
    except ValueError:
      for a in BaseVisitor.CHILD_ATTRS:
        if getattr(node, a, RefactorVisitor) is oldNode:
          setattr(node, a, newNode)
  @staticmethod
  def __createNode(tokenName, *args, **kwarg):
    node = jsparser.Node(RefactorVisitor.Tokenizer, jsparser.tokens[tokenName])
    node.start = -1
    node.end = -1
    for a in args:
      node.append(a)
      a._parent = node
    for k,v in kwarg.items():
      setattr(node, k, v)
    return node

class CreateGraphVisitor(BaseVisitor):
  def __init__(self, node):
    self.graph = Graph()
    # Текущий граф функции
    self.current = self.graph

    self.visit(node)

  # def filter(self, node):
    # return node.type != 'FUNCTION'
  def visit_SCRIPT(self, node):
    # Добавляем подграфы для всех функций внутри текущей функции.
    for f in node.funDecls:
      SubGraph(f.name, self.current)
  def visit_FUNCTION(self, node):
    if node.functionForm == 0:
      self.current = self.current.subgraph(node.name)
    else:
      print('WARNING: Skip anonymous function in line %d' % node.lineno)
  def after_visit_FUNCTION(self, node):
    if node.functionForm == 0:
      self.current = self.current.parent

class CallTraceVisitor(BaseVisitor):
  def run(self, node):
    for f in node.funDecls:
      if f.name=='OnIdle':
        self.__runFunc(f)
        break
  def filter(self, node):
    # Посещаем все узлы, кроме тех, которые не являются исполняемыми
    return node.type != 'FUNCTION'
  def visit_CALL(self, node, part):
    callable = node[0]
    if callable.type == 'DOT':
      # Если идет вызов метода у объекта, запоминаем порядок.
      self._traceCall(callable)
    else:
      try:
        # Если это обычный вызов функции, рекурсивно разбираем его.
        self.__call(node)
      except Exception as e:
        print('WARNING: %s' % e)
  # Приватные методы
  def __findFunction(self, name, node):
    while node is not None:
      funDecls = getattr(node, 'funDecls', None)
      if funDecls:
        for f in funDecls:
          if f.name == name:
            return f
      node = node._parent
    raise Exception('Call of undefined function `%s`' % name)
  def __runFunc(self, f):
    self._enterJSFunction(f)
    self.visit(f)
    self._leaveJSFunction(f)
  def __call(self, node):
    """Вызов JS-функции."""
    assert node.type == 'CALL', node
    assert len(node[0]) == 0, node
    name = node[0].value

    self._call(node)
    self.__runFunc(self.__findFunction(name, node._parent))

  # Методы для переопределения
  def _traceCall(self, node): pass
  def _call(self, node): pass
  def _enterJSFunction(self, f): pass
  def _leaveJSFunction(self, f): pass

class Visitor(CallTraceVisitor):
  def __init__(self, node, graph):
    self.__callstack = [graph]
    self.run(node)
    assert self.__callstack.pop() == graph, self.__callstack

  # Вызов JS-функции
  def _traceCall(self, node):
    assert node.type == 'DOT', node
    if node[1].value != 'Execute': return
    # Добавляем действие вызова метода у объекта в граф вызовов текущей функции.
    self._current.addAction(node[0].value) # Имя объекта, у которого вызыватеся функция
    print('%s+ %s' % ('| '*(len(self.__callstack)-1), self._name(node)))
  def _enterJSFunction(self, f):
    # Меняем текущий граф на тот, что соответствует вызванной функции.
    g = self._current.subgraph(f.name)
    self._current.addCall(g)
    self.__callstack.append(g)
    print('%s+ %s' % ('| '*(len(self.__callstack)-2), f.name))
  def _leaveJSFunction(self, f):
    self.__callstack.pop()
  @property
  def _current(self):
    return self.__callstack[-1]

class CreateExecuteTreeVisitor(CallTraceVisitor):
  INDENT = '| '
  class N(object):
    def __init__(self, node, parent):
      self.node = node
      self.parent = parent
      self.childs = []
      self.__hasTranObjects = None
      if parent:
        parent.childs.append(self)
    def print(self, indent=0):
      name = BaseVisitor._name(self.node) or '<<'+getattr(self.node, 'type', '')+'>>'
      print('%s+ %s' % (CreateExecuteTreeVisitor.INDENT*indent, name))
      for c in self.childs:
        c.print(indent+1)

      return False
    def cleanup(self):
      # Чистим детей
      for c in self.childs:
        c.cleanup()
      # Если мы имеем транзакционные объекты, очистка не требуется
      if self.node.type == 'DOT':
        self.__hasTranObjects = True
      # Если потомок имеет транзакционные объекты, оставляем его
      for c in self.childs[:]:
        if c.__hasTranObjects:
          self.__hasTranObjects = True
        else:
          self.childs.remove(c)

  def __init__(self, node):
    self.__indent = 0;
    self.__current = None
    self.__current = self.__newNode(node)
    self.run(node)
    assert self.__indent == 0, self.__indent
    assert self.__current.parent == None
    self.__current.cleanup()
    self.__current.print()
  # Вызов JS-функции
  def _traceCall(self, node):
    assert node.type == 'DOT', node
    if node[1].value != 'Execute': return
    self.__newNode(node)
    # print('%s+ %s' % (self.INDENT*self.__indent, self._name(node)))
  def _enterJSFunction(self, f):
    # print('%s+ %s' % (self.INDENT*self.__indent, f.name))
    self.__current = self.__newNode(f)
    self.__indent += 1
  def _leaveJSFunction(self, f):
    self.__indent -= 1
    self.__current = self.__current.parent
  def visit_IF(self, node, part):
    # print('%s+ <<%s>>' % (self.INDENT*self.__indent, node.value))
    self.__current = self.__newNode(node)
    self.__indent += 1
  def after_visit_IF(self, node, part):
    self.__indent -= 1
    self.__current = self.__current.parent
  visit_DO = visit_IF
  after_visit_DO = after_visit_IF
  visit_WHILE = visit_IF
  after_visit_WHILE = after_visit_IF
  def __newNode(self, node):
    return self.N(node, self.__current)

# True  - Сам узел подходит под фильтр (оставить узел и его потомков)
# False - Один из потомков узла подходит под фильтр (оставить узел, но попытаться удалить потомков)
# None  - Ни узел, ни его потомки не подходят под фильтр (удалить узел)
def cleanup(node, filter, indent=0):
  if filter(node): return True

  forRemove = []
  result = None
  for t in node._childs:
    # Если один из потомков имеет транзакционные объекты, то и данный узел их имеет
    r = cleanup(t[0], filter, indent+1)
    if r is True or r is False: result = False
    elif r is None: forRemove.append(t)

  # Не кромсаем дерево, а отсекаем только максимально возможные куски
  if result is False:
    for child, i in reversed(forRemove):
      try:
        if isinstance(i, int):
          del child._parent[i]
        else:
          setattr(child._parent, i, None)
      except:
        print([(n, i) for n,i in forRemove])
        print('[%s] child._parent=%s' % (i, child._parent))
        raise
  # print('%s%s [%s] %s' % ('  '*indent, node.type, BaseVisitor._name(node), result))
  return result

def _open(path):
  with open(path) as myFile:
    return jsparser.parse(myFile.read(), path)

from HTMLParser import HTMLParser
# create a subclass and override the handler methods
class MyHTMLParser(HTMLParser):
  tags = []
  def handle_starttag(self, tag, attrs):
    self.tags.append(tag)
    print("Encountered a start tag:", tag)
  def handle_endtag(self, tag):
    print("Encountered an end tag :", tag)
    self.tags.pop()
  def handle_data(self, data):
    if self.tags[-1] == 'script':
      print("Encountered some data  :", data)
if __name__ == "__main__":
  root = _open(sys.argv[1]);
  # Модифицируем граф, чтобы была возможность искать корректную вызываемую
  # функцию.
  AddParentVisitor(root);
  PrintVisitor(root)
  print('====================')
  RefactorVisitor(root);
  print('====================')
  # cleanup(root, lambda n: n.type == 'DOT' and n[-1].value == 'Execute')
  PrintVisitor(root)
  # CreateExecuteTreeVisitor(root)
  # g = CreateGraphVisitor(root).graph;
  # Visitor(root, g)
  # g.toDot(out=open('graph.dot', 'w+'))
  # PrintVisitor(root)
  # print(root)
# 130822000002055413
  # instantiate the parser and fed it some HTML
  # parser = MyHTMLParser()
  # parser.feed(open('''C:\Projects\TWRBS-3728\Screens\CashDeposit\ConfirmDeposit.htm''').read())