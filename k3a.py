# -*- coding: utf-8 -*-
from __future__ import print_function

__author__="ayanichkin"
__date__ ="$31.05.2013 13:15:03$"

from abc import ABCMeta
from abc import abstractmethod
import itertools# Для итератора по свойствам, событиям и документам
import sys
import glob   # Для получения файла проекта, когда путь задан к папке
import os
import shutil # Для очистки папки, в которую сохраняется проект
import xml.etree.ElementTree as ET

from Parser import ValueElementContentParser

__SUPPORTED_K3A_VERSIONS__ = [3]

__valueTagParser__ = ValueElementContentParser()


class MLS:
  NETWORK = 'NETWORK'
  DEFAULT = 'DEFAULT'

# Исключение, возбуждаемое декоратором enum, если параметр метода
# не является допустимым значением перечисления.
class ArgumentError(Exception):
  pass
# Декоратор, при применении к методу-сеттеру свойства класса проверяет,
# что устанавливаемое значение удовлетворяет ограничениям на допустимые значения.
def enum(*restrictions):
  # @type restrictions iterable
  # @type argument int
  def decorator(setter):
    def wrapper(self, value):
      if value not in restrictions:
        raise ArgumentError(u'Value must be one of %s, not %s' % (restrictions, value))
      return setter(self, value)
    return wrapper
  return decorator

def indent(elem, level=0):
  i = "\n" + level*"  "
  if len(elem):
    if not elem.text or not elem.text.strip():
      elem.text = i + "  "
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
    for elem in elem:
      indent(elem, level+1)
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
  else:
    if level and (not elem.tail or not elem.tail.strip()):
      elem.tail = i


class NotImplementedException(Exception):
  pass

# Список K3ABaseElement-ов, с возможностью получения их через индексацию
# и доступ к свойству по имени.
class Container(list):
  def __init__(self, iterable=[]):
    super(Container, self).__init__(iterable)
  def __getitem__(self, key):
    if isinstance(key, str):
      for e in self:
        if e.name == key: return e
    return super(Container, self).__getitem__(key)
  def __getattr__(self, key):
    if isinstance(key, str):
      for e in self:
        if e.name == key: return e
    return super(Container, self).__getattr__(key)


class K3ABaseElement(object):
  __metaclass__ = ABCMeta

  def __init__(self, k3aObject, name, content):
    self._name = name
    self._object = k3aObject

    # Содержимое элемента в виде строки.
    self._content = None
    # Содержимое элемента в виде разобранного содержимого
    self._parsedContent = None
    self._oldStyle = False

    self._parseContent(content)
    # print(u'  Create %s %s from %s' % (type(self), name, self._parsedContent))
  def __str__(self):
    return u'[%s] %s' % (type(self), self._name)
  def __repr__(self):
    return "<%s '%s'>" % (type(self).__name__, self._name)
  def __cmp__(self, other):
    if other is None: return int(self is None)
    return cmp(self._name, other._name)
  def __getattr__(self, name):
    return self._parsedContent.__getattr__(name)
  def __getitem__(self, name):
    return self._parsedContent[name]
################################################################################
  @property
  def name(self):
    return self._name
  @name.setter
  def name(self, name):
    self._name = name

################################################################################
  def asString(self):
    result = []
    self._toString(self._parsedContent, result)
    if self._oldStyle:
      return ''.join(result)
    else:
      return '{{{},%s}}' % (''.join(result))

  def _parseContent(self, strContent):
    self._content = strContent
    self._parsedContent = self._extractValue(__valueTagParser__.parse(strContent))

  def _extract(self, index):
    try:
      # В старом формате хранения некоторые значения могут отсутствовать,
      # поэтому возможно исключение.
      return self._parsedContent[index]
    except IndexError:
      pass

  def _setValue(self, index, value, enum = None):
    if (enum is not None) and (value not in enum):
      raise ArgumentError(u'Value must be one of %s, not %s' % (enum, value))
    if index >= 0:
      self._parsedContent[index] = value
    else:
      self._parsedContent = value

  @staticmethod
  def isOldStyle(parsedContent):
    # В новом стиле все элементы всегда внутри двойного списка,
    # причем список верхнего уровня всегда содержит один элемент.
    if isinstance(parsedContent, list):
      if not (len(parsedContent) == 1 and isinstance(parsedContent[0], list)):
        return True
    else:
      return True
    return False

  def _extractValue(self, parsedContent):
    if K3ABaseElement.isOldStyle(parsedContent):
      self._oldStyle = True
      return parsedContent;
    else:
      self._oldStyle = False
      return parsedContent[0][1]
  @staticmethod
  def _toString(value, result):
    if isinstance(value, list):
      result.append('{')
      it = iter(value)
      try:
        K3ABaseElement._toString(it.next(), result)
        for e in it:
          result.append(',')
          K3ABaseElement._toString(e, result)
      except StopIteration:
        pass
      result.append('}')
    elif isinstance(value, int):
      result.append(str(value).lower())# lower для bool-значений, т.к. True и False являются int-ами.
    elif value is None:
      result.append('null')
    elif isinstance(value, (str, unicode)):
      result.append('"')
      result.append(K3ABaseElement._escape(value))
      result.append('"')
    else:
      raise Exception(u'Unknown type: %s (for value %s)' % (type(value), value))
  @staticmethod
  def _escape(value):
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\000A')
    value = value.replace('\t', '\\0009')
    value = value.replace('&', '\\0026')
    value = value.replace('<', '\\003C')
    value = value.replace('>', '\\003E')
    return value;

class K3AProperty(K3ABaseElement):

  def __init__(self, k3aObject, name, content):
    super(K3AProperty, self).__init__(k3aObject, name, content)
    # Структура:
    # {
    #   {
    #     null,             - здесь всегда или null или {}
    #     "GetContractInfo" - Значение поля (может быть списком для списочных полей*)
    #   }
    # }
    # 
    # * Список записывается, как значения в фигурных скобках.
  
  def __str__(self):
    return u'%s=%s' % (self.name, self.value)

  @property
  def value(self):
    return self._parsedContent;
  @value.setter
  def value(self, value):
    self._setValue(-1, value)

class K3AEvent(K3ABaseElement):
  
  def __init__(self, k3aObject, name, content):
    # Структура распарсенного контента
    # [
    #   "NavigateAndCallHandler",       - Тип обработчика (NavigateAndCallHandler|CallHandler|RunScript)
    #   "Common\\ConfirmSurcharge.htm", - Путь к экрану для перехода
    #   true,                           - Синхронный (False) или асинхронный (True) вызов обработчика
    #   "",                             - Фрейм для перехода ("" - по умолчанию)
    #   "",                             - Имя обработчика ("" - имя по умолчанию, как On<имя_события>)
    #   ""                              - Исходный код скрипта (используется при типе RunScript)
    # ]
    super(K3AEvent, self).__init__(k3aObject, name, content)

  def __str__(self):
    return 'K3AEvent(name=%s, type=%s, screen=%s, isAsync=%s, handler=%s)' % (self.name, self.type, self.screen, self.isAsync, self.handlerName)

  def storedName(self):
    return '_Event%s' % self._name

  @property
  def type(self):
    return self._extract(0)
  @property
  def screen(self):
    return self._extract(1)
  @property
  def isAsync(self):
    return self._extract(2)
  @property
  def frame(self):
    return self._extract(3)
  @property
  def handlerName(self):
    return self._extract(4) or 'On'+self._name
  @property
  def script(self):
    return self._extract(5)
    
  @type.setter
  @enum('NavigateAndCallHandler', 'CallHandler', 'RunScript')
  def type(self, value):
    self._parsedContent[0] = value
  @screen.setter
  def screen(self, value):
    self._parsedContent[1] = value
  @isAsync.setter
  def isAsync(self, value):
    self._parsedContent[2] = bool(value)
  @frame.setter
  def frame(self, value):
    self._parsedContent[3] = value
  @handlerName.setter
  def handlerName(self, value):
    try:
      self._parsedContent[4] = value
    except IndexError:
      self._parsedContent.append(value)
  @script.setter
  def script(self, value):
    try:
      self._parsedContent[5] = value
    except IndexError:
      if len(self._parsedContent) == 4:
        self._parsedContent.append('')
      self._parsedContent.append(value)

class K3ADocument(K3ABaseElement):
  # Отображение (str=>str) placehoder-ов в документе на их значения.
  #
  # - Если в кавычках, то это статический текст;
  # - Если ничем не обрамлено, это имя поля у объекта в сценарии;
  # - Если начинается с #, то это ключ в ScratchPad-е;
  # - Если начинается с $, то это ключ в LocalLanguage.
  # _fields = dict()

  def __init__(self, k3aObject, name, content):
    super(K3ADocument, self).__init__(k3aObject, name, content)
    # Структура
    # {
    #   {
    #     { },
    #     {
    #       { "a=value" },      - Список значений подставляемых полей в виде <имя поля>=<значение поля>*
    #       "ReceiptPrinter",   - Принтер, который будет печатать форму**
    #       "Form",             - Источник печати (Form|Template|File)
    #       "",                 - Название формы ("" - не задана) (актуально для источника Form)
    #       "",                 - Шаблон печати (актуально для источника Template)
    #       "",                 - Имя файла, для источника File
    #       false,              - Удалять ли файл после печати (актуально для источника File)
    #       "",                 - Текст со скриптом форматирования
    #       false               - Копировать ли в журнал
    #     }
    #   }
    # }
    # * Трактовка значений полей:
    #   - Если в кавычках, то это статический текст;
    #   - Если ничем не обрамлено, это имя поля у объекта в сценарии;
    #   - Если начинается с #, то это ключ в ScratchPad-е;
    #   - Если начинается с $, то это ключ в LocalLanguage.
    # ** Список принтеров, доступных для всех источников печати:
    #   ReceiptPrinter
    #   StatementPrinter
    #   JournalPrinter
    #   PassbookPrinter
    #   Scanner
    # Список принтеров, доступных при печати из Template и File
    #   Depository
    #   Journal (галочка Копировать в журнал для него не доступна)
    #   BundleScanner
    self._parseDynamicFields(self._extract(0))

  @property
  def fields(self):
    return self._fields
  @property
  def printerType(self):
    return self._extract(1)
  @property
  def sourceType(self):
    return self._extract(2)
  @property
  def formName(self):
    return self._extract(3)
  @property
  def template(self):
    return self._extract(4)
  @property
  def fileName(self):
    return self._extract(5)
  @property
  def deleteFileAfterComplete(self):
    return self._extract(6)
  @property
  def formattingScript(self):
    return self._extract(7)
  @property
  def copyToJornal(self):
    return self._extract(8)
  
  def _parseDynamicFields(self, fieldList):
    self._fields = dict()
    if fieldList is None:
      return
    for field in fieldList:
      s = field.split('=')
      self._fields[s[0]] = s[1]

# Соответствует одному элементу /TREESTORE/NAMESPACES/NAMESPACE в конфигурационных XML-файлах.
class K3AObjectInfo(object):
  def __init__(self, namespace):
    # @type project K3AProject
    # @type namespace ElementTree - Элемент TREESTORE.NAMESPACES.NAMESPACE

    # Массив из частей имени объекта.
    self._fullName = None

    # Список (Container) свойств объекта (K3AProperty).
    self._properties = None
    # Список (Container) событий объекта (K3AEvent).
    self._events = None
    # Список (Container) документов объекта (K3ADocument).
    self._documents = None

    self._parse(namespace)
  def __repr__(self):
    return 'K3AObjectInfo(class=%s, type=%s, name=%s, %s/%s/%s)' % (
      self.cls,
      self.type,
      self.name,
      len(self._properties),
      len(self._events),
      len(self._documents)
    )
  def __iter__(self):
    u"""Возвращает итератор по всем внутренним элементам (сначала свойства, потом события, потом документы)."""
    return itertools.chain(self._properties, self._events, self._documents)
  def __cmp__(self, other):
    if other is None: return int(self is None)
    return cmp(self.fullName, other.fullName)
################################################################################
  @property
  def fullName(self):
    return '.'.join(self._fullName)
  # Класс объекта - 'SupervisorApp' | 'CustomerApp' | 'Common'
  @property
  def cls(self):
    return self._fullName[0]
  # .NET тип объекта.
  @property
  def type(self):
    if len(self._fullName) == 3:
      return self._fullName[1]
    return None
  @type.setter
  def type(self, type):
    if len(self._fullName) == 3:
      self._fullName[1] = type
  # Имя объекта.
  @property
  def name(self):
    return self._fullName[-1]
  @name.setter
  def name(self, name):
    self._fullName[-1] = name
  @property
  def properties(self):
    return self._properties
  @property
  def events(self):
    return self._events
  @property
  def documents(self):
    return self._documents
################################################################################
  # parent - ElementTree.Element с именем 'NAMESPACE'
  # level = NETWORK | DEFAULT
  def write(self, parent, projectName, level):
    # @type parent ElementTree
    # @type projectName str
    # @type level str
    # @type e K3ABaseElement
    parent.set('Name', 'K3A.%s.%s.%s' % (projectName, self.fullName, level))

    parent.append(ET.Comment('======== Properties ========'))
    self._properties.sort()
    for e in self._properties:
      val = ET.SubElement(parent, 'VALUE', {'Name': e._name})
      val.text = e.asString()

    parent.append(ET.Comment('========== Events =========='))
    self._events.sort()
    for e in self._events:
      val = ET.SubElement(parent, 'VALUE', {'Name': '_Event'+e._name})
      val.text = e.asString()

    parent.append(ET.Comment('========= Documents ========'))
    self._documents.sort()
    for e in self._documents:
      val = ET.SubElement(parent, 'VALUE', {'Name': 'Document'+e._name})
      val.text = e.asString()

  def dump(self, file=sys.stdout, indent=0):
    lvl = '  '*indent

    print(u'%s#### %s ####' % (lvl, self))
    lvl += '  '
    print(u'%s---- Properties ----' % lvl, file=file)
    for e in self._properties:
      print(u'%s%s' % (lvl, e), file=file)
    print(u'%s------ Events ------' % lvl, file=file)
    for e in self._events:
      print(u'%s%s' % (lvl, e), file=file)
    print(u'%s----- Documents ----' % lvl, file=file)
    for e in self._documents:
      print(u'%s%s' % (lvl, e), file=file)
  
  def renameItem(self, category, name, newName):
    u"""
    Переименовывает свойство, событие или документ с указанным именем и возвращает True.
    Если элемента с таким именем не существуют, возвращает False.
    """
    for e in getattr(self, category):
      if e.name == name:
        if category == 'events':
          h = e.handlerName
          e.name = newName
          e.handlerName = h
        else:
          e.name = newName
        return True
    return False
################################################################################
# Приватная часть
################################################################################
  def _parse(self, namespace):
    self._parseNameAttribute(namespace.attrib['Name'])
    self._properties= Container()
    self._events    = Container()
    self._documents = Container()
    for value in namespace.findall('VALUE'):
      self._parseValueElement(value)
  def _parseNameAttribute(self, attr):
    attr = attr.split('.');
    # Структура:
    # [0] 'K3A'
    # [1] <имя проекта>
    # [x] \
    # [x]  } <название объекта (состоит из 2-3 частей)>
    # [x] /
    # [-1]<тип настроек (NETWORK|DEFAULT)> (отсутствует в MLS.Stores)
    #
    if attr[-1] in (MLS.DEFAULT, MLS.NETWORK):
      self._fullName = attr[2:-1]
    else:
      self._fullName = attr[2:]
  def _parseValueElement(self, value):
    name = value.attrib['Name']

    if name.startswith('_Event'):
      self._events.append(K3AEvent(self, name[6:], value.text))# Пропускаем '_Event'
    elif name.startswith('Document'):
      self._documents.append(K3ADocument(self, name[8:], value.text))# Пропускаем 'Document'
    else:
      self._properties.append(K3AProperty(self, name, value.text))


class K3AObject(object):
  def __init__(self, obj):
    # @type obj K3AObjectInfo
    self._object  = obj
    # K3AObjectInfo
    self._default = None
  def __iter__(self):
    return itertools.chain(self.properties, self.events, self.documents)
  def __str__(self):
    return 'K3AObject(class=%s, type=%s, name=%s)' % (self.cls, self.type, self.name)
  __repr__ = __str__
  def __hash__(self):
    return hash(self.fullName)
  def __cmp__(self, other):
    return cmp(self.fullName, other.fullName)
  def __items(self, prop):
    # Все элементы по умолчанию
    if self._default is not None:
      items = Container(p for p in getattr(self._default, prop))
    else:
      items = Container()
    if self._object is not None:
      for p in getattr(self._object, prop):
        for i, pp in enumerate(items):
          # Если объект имеет свой элемент, удаляем умолчание.
          if pp.name == p.name:
            del items[i]
            break
        items.append(p)
      items.sort(key=lambda p: p.name)
    return items
################################################################################
  def dump(self, file=sys.stdout):
    s = str(self)
    print('#'*(len(s)+4))
    print('| '+s+' |', file=file)
    print('#'*(len(s)+4))
    try:
      self.dumpProperties(file)
      self.dumpEvents(file)
      self.dumpDocuments(file)
    except:
      print(self, file=sys.stderr)
      print(dir(self), file=sys.stderr)
      raise

  def dumpProperties(self, file=sys.stdout):
    print(u'  ===== PROPERTIES =====', file=file)
    print(u'    [default]', file=file)
    if self._default is not None:
      for p in self._default.properties:
        print(u'      %s' % p, file=file)
    print(u'    [own]', file=file)
    if self._object is not None:
      for p in self._object.properties:
        print(u'      %s' % p, file=file)
    print(file=file)
  def dumpEvents(self, file=sys.stdout):
    print(u'  ======= EVENTS =======', file=file)
    print(u'    [default]', file=file)
    if self._default is not None:
      for p in self._default.events:
        print(u'      %s' % p, file=file)
    print(u'    [own]', file=file)
    if self._object is not None:
      for p in self._object.events:
        print(u'      %s' % p, file=file)
    print(file=file)
  def dumpDocuments(self, file=sys.stdout):
    print(u'  ====== DOCUMENTS =====', file=file)
    print(u'    [default]', file=file)
    if self._default is not None:
      for p in self._default.documents:
        print(u'      %s' % p, file=file)
    print(u'    [own]', file=file)
    if self._object is not None:
      for p in self._object.documents:
        print(u'      %s' % p, file=file)
    print(file=file)
################################################################################
  @property
  def fullName(self):
    if self._object is not None:
      return self._object.fullName
    return self._default.fullName
  @property
  def cls(self):
    if self._object is not None:
      return self._object.cls
    return self._default.cls
  @property
  def type(self):
    if self._object is not None:
      return self._object.type
    return self._default.type
  @property
  def name(self):
    if self._object is not None:
      return self._object.name
    return self._default.name
  @property
  def properties(self):
    return self.__items('properties')
  @property
  def events(self):
    return self.__items('events')
  @property
  def documents(self):
    return self.__items('documents')
################################################################################
  def renameItem(self, category, name, newName):
    u"""Переименовывает элемент. Возвращает True, если переименование было совершено, иначе False."""
    r = False
    if self._object is not None:
      r = self._object.renameItem(category, name, newName)
    return self._default.renameItem(category, name, newName) or r
  def renameProperty(self, name, newName):
    return self.renameItem('properties', name, newName)
  def renameEvent(self, name, newName):
    return self.renameItem('events', name, newName)
  def renameDocument(self, name, newName):
    return self.renameItem('documents', name, newName)

# Описывает конфигурационный XML-файл, содержащий список K3AObjectInfo.
class K3AConfigFile(object):
  def __init__(self, path, level):
    u"""
    path - строка с полным путем к конфигурационному файлу.
    level - MLS.DEFAULT | MLS.NETWORK - строка с уровнем хранилища.
    """
    # @type path str
    # Путь, по которому был загружен данный файл.
    self._path = path
    self._level = level
    # Имя конфигурационного файла
    self._name = '.'.join(os.path.basename(self._path).split('.')[2:-2])
    # Список объектов K3AObjectInfo, найденных в этом файле.
    self._objects = self._parse()
    # Хранит признак того, что конфигурационный файл изменился и при записи его надо сохранить.
    self._hasChanges = False

  def __cmp__(self, other):
    if other is None: return int(self is None)
    return cmp(self._path, other._path)
  def __repr__(self):
    return 'K3AConfigFile(%s, %s)' % (self.name, self._level)
################################################################################
  @property
  def path(self):
    u"""Полный путь к файлу."""
    return self._path
  @property
  def name(self):
    return self._name
  @path.setter
  def path(self, value):
    self._hasChanges = self._hasChanges or self._path != value
    self._path = value
################################################################################
  def save(self, projectName, force=False):
    if not (self._hasChanges or force):
      return
    root = ET.Element('TREESTORE')
    ns = ET.SubElement(root, 'NAMESPACES')

    self._writeObjects(ns, projectName)

    dir = os.path.dirname(self.path)
    if not os.path.exists(dir):
      os.makedirs(dir)
    indent(root)
    ET.ElementTree(root).write(self.path, 'utf-8', True)# Включаем XML-декларацию, для UTF-8 по умолчанию ее нет
    self._path = self.path

  def objects(self, *names):
    u"""
    Возвращает список объектов с указанными именами.
    Если имена не заданы, возвращаются все объекты.
    """
    if len(names) == 0: return self._objects
    return [o for o in self._objects if o.name in names]
################################################################################
  def _parse(self):
    u"""
    Разбирает указанный файл, возвращает список K3AObjectInfo
    (соответсвующих элементам ./NAMESPACES/NAMESPACE), найденных в нем.
    """
    # @type tree ElementTree
    # @type objects list
    tree = ET.parse(self._path);
    objects = []
    for namespace in tree.findall('./NAMESPACES/NAMESPACE'):
      objects.append(K3AObjectInfo(namespace))
    return objects
  def _writeObjects(self, ns, projectName):
    for o in self._objects:
      o.write(ET.SubElement(ns, 'NAMESPACE'), projectName, self._level)

class K3AMLSStoresConfigFile(K3AConfigFile):
  def __init__(self, path, level):
    super(K3AMLSStoresConfigFile, self).__init__(path, level)
    self._name = 'MLS.Stores'
  def _writeObjects(self, ns, projectName):
    for o in self._objects:
      val = ET.SubElement(ns, 'NAMESPACE')
      o.write(val, projectName, self._level)
      val.set('Name', 'K3A.%s.%s' % (projectName, o.fullName))

class K3AProject(object):

  def __init__(self, path):
    # @type self K3AProject
    # @type path str

    # Полный путь к папке, в которой лежит файл .k3a проекта.
    self._path = None;
    # Имя проекта K3A.
    self._name = None;
    # Версия (на текущий момент всегда 3).
    self._version = None;
    # Список путей к дополнительным .NET-сборкам, используемых проектом.
    self._assemblies = None;
    # Отображение имени объекта на K3AObject, содержащий настройки объекта
    # и настройки по умолчанию.
    self._objects = None;
    # Список со всеми файлами конфигурации проекта (K3AConfigFile).
    self._configFiles = None;
    # Список с файлами MLS.Stores.xml (K3AMLSStoresConfigFile).
    self._mlsStoresConfigFiles = None;

    print(u'Process path %s' % path)
    # Если переданный путь является папкой, берем первый файл из него.
    if os.path.isdir(path):
      path = glob.glob(os.path.join(path, '*.k3a'))[0]
    self._parse(path)
  def __repr__(self):
    return 'K3AProject(name=%s, path=%s, objects=%s)' % (self._name, self._path, len(self._objects))
################################################################################
# Публичная часть
################################################################################
  @property
  def dir(self):
    u"""Возвращает абсолютный путь к папке, в которой лежит проект."""
    return self._path
  @property
  def name(self):
    u"""Возвращает название проекта K3A."""
    return self._name;
  @property
  def k3aFile(self):
    u"""Возвращает полный путь к файлу проекта K3A."""
    return os.path.join(self.dir, self.name+'.k3a');
  @property
  def customerJSPath(self):
    return os.path.join(self.dir, 'Script', 'Customer.js')
  @property
  def supervisorJSPath(self):
    return os.path.join(self.dir, 'Script', 'Supervisor.js')
  @dir.setter
  def dir(self, value):
    self._path = os.path.abspath(value)
  @name.setter
  def name(self, value):
    self._name = value

  # Возвращает итератор по парам (полное_имя_к_сборке, версия_файла_сборки),
  # гда версия_файла_сборки - кортеж, состоящий из цифр версии.
  # Если в файле сборки не указана версия, то кортеж пустой.
  def versions(self):
    for path in self._assemblies:
      if not os.path.isabs(path):
        path = os.path.join(self.dir, path)
      yield path, self._getFileVersion(path)
  def versionTXSST(self):
    for p, v in filter(lambda x: os.path.basename(x[0]).upper()=='TXSST.DLL', self.versions()):
      return v
    return tuple()
################################################################################
  def configFiles(self, *names):
    u"""Возвращает список файлов конфигурации, чье имя содержится в names."""
    if len(names) == 0:
      return self._configFiles
    return [conf for conf in self._configFiles if conf.name in names]
  def objects(self, *types):
    u"""
    Получает список объектов с указанными типами.

    types - список имен .NET типов, объекты которых нужно получить. Если не задано, то возвращаются все объекты.
    """
    if len(types) == 0:
      return self._objects.values()
    return [o for o in self._objects.itervalues() if o.type in types]
  def objectProps(self, type, prop):
    u"""
    Возвращает генератор, который обходит все объекты проекта указанного типа type
    и извлекает из каждого свойство с именем prop (типа K3ABaseElement).
    """
    for o in self._objects.itervalues():
      if o.type == type:
        yield o.properties[prop], o

  def save(self, force=False, deleteUnusedFiles = False):
    u"""
    Сохраняет проект по пути self.dir.
    
    force - пересохранить даже не затронутые обновлением файлы (не реализовано).
    deleteUnusedFiles - если True, папка конфигурации будет очищена перед сохранением.
    """

    if deleteUnusedFiles:
      self._clearFolder(path)

    self._saveK3AFile();

    for conf in self._mlsStoresConfigFiles:
      conf.path = os.path.join(self._levelToPath(conf._level), conf.name+'.xml')
      conf.save(self.name, force)
      print(u'[Saved] %s' % conf.path)

    for conf in self._configFiles:
      conf.path = self._pathToFile(conf.name, conf._level)
      conf.save(self.name, force)
      print(u'[Saved] %s' % conf.path)

  def dump(self, file=sys.stdout, detail=0):
    print(repr(self), file=file)
    values = self._objects.values()
    values.sort()
    for o in values:
      if detail == 1:
        print(u'  %s\t%s' % o, file=file)
      else:
        o.dump(file)

################################################################################
# Приватная часть
################################################################################
  def _parse(self, path):
    self._path = os.path.dirname(os.path.abspath(path))

    self._parseK3AFile(path)
    self._parseConfiguration()
  def _parseK3AFile(self, path):
    u"""
    Разбирает файл *.k3a, который содержит имя проекта и версию конфигурации.
    """
    print(u'[Parse] K3A project file: %s' % path)
    tree = ET.parse(path)
    for name in tree.getiterator('ProjectName'):
      self._name = name.text
      break;
    for version in tree.getiterator('Version'):
      self._version = int(version.text)
      break;

    if self._version not in __SUPPORTED_K3A_VERSIONS__:
      print(u'WARNING: Project version (%s) do not match supported parser versions (%s), parse may be incorrect' % (self._version, __SUPPORTED_K3A_VERSIONS__))
  def _parseConfiguration(self):
    # @type objects list
    # Генератор частей имен файлов из имен объектов.
    # Просто отбрасывает все после второй точки.
    def names(objects):
      for n,l in objects:
        yield '.'.join(n.split('.')[:2])

    self._configFiles = []
    self._mlsStoresConfigFiles = []
    self._assemblies = []# Заполняется в _parseCommon
    self._objects = dict()

    # objects содержит список кортежей строк (имя_объекта, местоположение_объекта_в_дереве_дизайнера)
    objects = self._parseCommon(MLS.DEFAULT)
    objects.extend(self._parseCommon(MLS.NETWORK))
    # Удаляем дубликаты
    objects = set(objects)
    objectFullNames = map(lambda x: x[0], objects)

    # Извлекаем части имен файлов из имен объектов, удаляем дубликаты и сортируем
    # для эстетического восприятия.
    fileNames = sorted(set(names(objects)))
    for n in fileNames:
      conf = self._parseConfigFile(n, MLS.NETWORK)
      if conf is not None:
        for o in conf.objects():
          # Достаем только те объекты, которые есть в проекте
          if o.fullName in objectFullNames:
            self._objects[o.name] = K3AObject(o)

    for n in fileNames:
      conf = self._parseConfigFile(n, MLS.DEFAULT)
      if conf is not None:
        for o in conf.objects():
          # Достаем только те объекты, которые есть в проекте
          if o.fullName in objectFullNames:
            try:
              # @type obj K3AObject
              obj = self._objects[o.name]
            except KeyError:
              self._objects[o.name] = obj = K3AObject(None)
            obj._default = o

    self._parseSpecialConfigs()

  @enum(MLS.DEFAULT, MLS.NETWORK)
  def _parseCommon(self, level):
    u"""
    Разбирает файлы K3A.<имя_проекта>.Common.NETWORK.xml и Defaults/K3A.<имя_проекта>.Common.DEFAULT.xml.
    
    Возвращает кортеж списков (сборки_проекта, имя_и_тип_объектов, иерархическое_положение_объектов)
    """

    objectNames = []
    objectLocations = []

    conf = self._parseConfigFile('Common', level)
    if conf is not None:
      for o in conf.objects('Config'):
        for p in o.properties:
          if p.name == 'ApplicationObjects':
            objectNames.extend(p.value)
          elif p.name == 'ApplicationObjectLocations':
            objectLocations.extend(p.value)
          elif p.name == 'ImportedAssemblies':
            self._assemblies.extend(p.value)
          else:
            print('[Parse] <unknown>', p)

    return zip(objectNames, objectLocations)
  @enum(MLS.DEFAULT, MLS.NETWORK)
  def _parseMLSStores(self, level):
    path = self._levelToPath(level)
    path = os.path.join(path, 'MLS.Stores.xml')

    if os.path.exists(path):
      print(u'[Parse] %s' % path)
      conf = K3AMLSStoresConfigFile(path, level)
      self._mlsStoresConfigFiles.append(conf)
      return conf
  def _parseConfigFile(self, configName, level):
    u"""
    Разбирает конфигурационный файл с именем 'K3A.${self.name}.${configName}.${level}.xml',
    если он существует и возвращает объект K3AConfigFile, соответсвующий ему. Если такого файла
    нет, возвращает None.
    """
    path = self._pathToFile(configName, level)

    if os.path.exists(path):
      print(u'[Parse] %s' % path)
      conf = K3AConfigFile(path, level)
      self._configFiles.append(conf)
      return conf
  def _parseSpecialConfigs(self):
    self._parseMLSStores(MLS.DEFAULT)
    self._parseMLSStores(MLS.NETWORK)
    
    # Специальные файлы, не объявлены в списке загружаемых, просто всегда должны грузиться.
    self._parseConfigFile('UserInterface', MLS.DEFAULT)
    self._parseConfigFile('UserInterface', MLS.NETWORK)

    self._parseConfigFile('WebOperator', MLS.DEFAULT)
    self._parseConfigFile('WebOperator', MLS.NETWORK)
    
################################################################################
  def _saveK3AFile(self):
    path = self.k3aFile
    if not os.path.exists(os.path.dirname(path)):
      os.makedirs(os.path.dirname(path))

    root = ET.Element('K3A')
    ET.SubElement(root, 'ProjectName').text = self.name
    ET.SubElement(root, 'Version').text = str(self._version)

    indent(root)
    ET.ElementTree(root).write(path, 'UTF-8', True)# Включаем XML-декларацию, для UTF-8 по умолчанию ее нет
    print(u'[Saved] %s' % path)
################################################################################
  def _levelToPath(self, level):
    path = os.path.join(self.dir, 'Configuration')
    if level == MLS.DEFAULT:
      path = os.path.join(path, 'Defaults')
    return path
  def _pathToFile(self, configName, level):
    u"""
    Получает путь до файла конфигурации проекта в соответствии с указанным уровнем хранилища.
    
    level - MLS.DEFAULT | MLS.NETWORK
    """
    path = self._levelToPath(level)
    fileName = 'K3A.%s.%s.%s.xml' % (self.name, configName, level);
    return os.path.join(path, fileName)
  @staticmethod
  def _getFileVersion(path):
    u"""
    Получает версию файла в виде строки 'major.minor.revision.build'.
    Если файл не содержит секции с ресурсом FILEINFO, возвращает '?.?.?.?'.

    path - Полный путь к файлу.
    """
    # @type filename str
    try:
      import pefile
      pe = pefile.PE(path)
      # Версия в виде 64-битного числа, по 8 бит на каждую из четырех частей версии.
      # version = (pe.VS_FIXEDFILEINFO.FileVersionMS << 32) + pe.VS_FIXEDFILEINFO.FileVersionLS
      for fi in pe.FileInfo:
        if fi.Key == 'StringFileInfo':
          for st in fi.StringTable:
            # @type entry tuple
            for entry in st.entries.items():
              if entry[0] == 'FileVersion':
                return tuple(entry[1].split('.'))
                # return tuple(map(int, entry[1].split('.')))
    except:
      print(u"WARNING: File %s don't contain file version" % path)
      print(sys.exc_info())
    return tuple()
  @staticmethod
  def _clearFolder(folder):
    for file in os.listdir(folder):
      path = os.path.join(folder, file)
      try:
        if os.path.isfile(path):
          os.unlink(path)
        else:
          shutil.rmtree(path)
        print(u'[Deleted] %s' % path)
      except:
        print(str(sys.exc_info()[1]))


class Upgrader(object):
  __metaclass__ = ABCMeta
  def __init__(self):
    self._updated = set()

  @abstractmethod
  def upgrade(self, project): pass
  # Возвращает кортеж из цифр минимальной версии, которую он может апгрейдить.
  @abstractmethod
  def minVersion(self): pass
  # Возвращает кортеж из цифр максимальной версии, которую он может апгрейдить.
  @abstractmethod
  def maxVersion(self): pass
  def log(self, *values):
    print(*values)
  def _logAffected(self, affected):
    self.log()
    msg = u'  Affected objects (%d total):' % len(affected);
    self.log(msg)
    self.log(u'  ' + u'~'*(len(msg)-2))
    for o in sorted(affected):
      self.log(u'    %s' % o.name)
      self._updated.add(o)