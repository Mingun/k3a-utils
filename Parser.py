# -*- coding: utf-8 -*-
# Портировано с JavaScript-кода парсера, созданного PEG.js 0.7.0.
# http://pegjs.majda.cz/
# Грамматика pegjs:
#
# _ 'Whitespace' = [ \t\r\n]*
# hex
#   = [a-fA-F0-9]
# hex4
#   = h:(hex hex hex hex) {return parseInt(h.join(''), 16);}
# char
#  = '\\' h:hex4 {return String.fromCharCode(h);}
#  / '\\' c:. {return c;}
#  / [^"]
# string 'String'
#   = '"' s:char* '"' {return s.join('');}
# number 'Number'
#   = n:('-'? [0-9]+) {return parseInt(n.join(''), 10);}
# 
# value
#   = '{' _ l:list _ '}' {return l;}
#   / 'null'
#   / 'true'
#   / 'false'
#   / number
#   / string
# list
#   = h:value t:(_ ',' _ v:value {return v;}) {t.unshift(h);return t;}

__author__="ayanichkin"

import re

def escape(ch):
  charCode = ord(ch[0]);
  escapeChar = Null;
  length = Null;
  
  if charCode <= 0xFF:
    escapeChar = 'x';
    length = 2;
  else:
    escapeChar = 'u';
    length = 4;

  return '\\' + escapeChar + hex(charCode)[2:].upper().rjust(length, '0');
def quote(s):
  # ECMA-262, 5th ed., 7.8.4: All characters may appear literally in a
  # string literal except for the closing quote character, backslash,
  # carriage return, line separator, paragraph separator, and line feed.
  # Any character may appear in the form of an escape sequence.
  #
  # For portability, we also escape escape all control and non-ASCII
  # characters. Note that "\0" and "\v" escape sequences are not used
  # because JSHint does not like the first and IE the second.
  return re.escape(s)
  s = s.replace('\\', '\\\\')  # backslash
  s = s.replace('"', '\\"')    # closing quote character
  s = s.replace('\x08', '\\b') # backspace
  s = s.replace('\t', '\\t')   # horizontal tab
  s = s.replace('\n', '\\n')   # line feed
  s = s.replace('\f', '\\f')   # form feed
  s = s.replace('\r', '\\r')   # carriage return
  # s = s.replace('[\x00-\x07\x0B\x0E-\x1F\x80-\uFFFF]', escape)
  
  return "'%s'" % s;

# Специальный класс для указания того, что функция не смогла распарсить значение.
# Нельзя использовать None, т.к. сам None может быть валидным значением функции.
class Null(object):
  pass

class ParserError(Exception):
  pass

# Кидается, когда парсер встречает синтаксическую ошибку.
class SyntaxError(ParserError):
  def __init__(self, expected, found, offset, line, column):
    super(ParserError, self).__init__(self.buildMessage(expected, found), {'offset':offset, 'line':line, 'column':column})
    self.expected = expected;
    self.found = found;
    self.offset = offset;
    self.line = line;
    self.column = column;
  
  @staticmethod
  def buildMessage(expected, found):
    expectedHumanized = Null
    foundHumanized = Null;
    l = len(expected)

    if l == 0:
      expectedHumanized = u'end of input';
    elif l == 1:
      expectedHumanized = expected[0];
    else:
      expectedHumanized = u'%s or %s' % (', '.join(expected[0:l-1]), expected[l-1]);

    foundHumanized = found and quote(found) or u'end of input';

    return u'Expected %s but %s found.' % (expectedHumanized, foundHumanized);

class ValueElementContentParser(object):
  rec_      = re.compile('^[ \t\r\n]')
  rec_char  = re.compile('^[^"]')
  rec_number= re.compile('^[0-9]')
  rec_hex   = re.compile('^[0-9a-fA-F]')

  def __init__(self):
    self.parseFunctions = {
      "_"     : self.__parse_whitespace,
      "value" : self.__parse_value,
      "list"  : self.__parse_list,
      "string": self.__parse_string,
      "char"  : self.__parse_char,
      "hex"   : self.__parse_hex,
      "hex4"  : self.__parse_hex4,
      "number": self.__parse_number
    };

  #
  # Parses the input with a generated parser. If the parsing is successfull,
  # returns a value explicitly or implicitly specified by the grammar from
  # which the parser was generated (see |PEG.buildParser|). If the parsing is
  # unsuccessful, throws |PEG.parser.SyntaxError| describing the error.
  #
  def parse(self, input, startRule = None):

    self.pos = 0;
    self.reportFailures = 0;
    self.rightmostFailuresPos = 0;
    self.rightmostFailuresExpected = [];

    if startRule is not None:
      if self.parseFunctions[startRule] is None:
        raise ParserError(u'Invalid rule name: %s.' % quote(startRule));
    else:
      startRule = 'value';

    result = self.parseFunctions[startRule](input);

    #
    # Сейчас парсер в одном из следующих трех состояний:
    #
    # 1. Парсер успешно разобрал весь вход.
    #
    #    - |result is not Null|
    #    - |self.pos == len(input)|
    #    - |rightmostFailuresExpected| может содержать что-то, а может и нет
    #
    # 2. Парсер успешно разобрал только часть входа.
    #
    #    - |result is not Null|
    #    - |self.pos < len(input)|
    #    - |rightmostFailuresExpected| может содержать что-то, а может и нет
    #
    # 3. Парсер не смог разобрать ни одну часть входа.
    #
    #   - |result == Null|
    #   - |self.pos == 0|
    #   - |rightmostFailuresExpected| содержит как минимум одно значение
    #
    # All code following this comment (including called functions) must
    # handle these states.
    #
    if result is Null or self.pos != len(input):
      offset = max(self.pos, self.rightmostFailuresPos);
      found = offset < len(input) and input[offset] or Null;
      errorPosition = self.__computeErrorPosition(offset, input);

      raise SyntaxError(
        self.__cleanupExpected(self.rightmostFailuresExpected),
        found,
        offset,
        errorPosition[0],
        errorPosition[1]
      );

    return result;

  # Парсеры правил

  def __parse_whitespace(self, input):
    result0 = result1 = Null;

    self.reportFailures += 1;
    result0 = [];

    if self.rec_.match(self.char(input, self.pos)):
      result1 = self.char(input, self.pos);
      self.pos += 1;
    else:
      result1 = Null;
      if self.reportFailures == 0:
        self.__matchFailed('[ \\t\\r\\n]');
    while result1 is not Null:
      result0.append(result1);
      if self.rec_.match(self.char(input, self.pos)):
        result1 = self.char(input, self.pos);
        self.pos += 1;
      else:
        result1 = Null;
        if self.reportFailures == 0:
          self.__matchFailed('[ \\t\\r\\n]');
    self.reportFailures -= 1;
    if self.reportFailures == 0 and result0 is Null:
      self.__matchFailed('Whitespace');
    return result0;

  def __parse_value(self, input):
    result0 = result1 = result2 = result3 = result4 = Null;
    pos0 = pos1 = self.pos;

    if ord(self.char(input, self.pos)) == 123:# {
      result0 = '{';
      self.pos += 1;
    else:
      result0 = Null;
      if self.reportFailures == 0:
        self.__matchFailed("'{'");
    if result0 is not Null:
      result1 = self.__parse_whitespace(input);
      if result1 is not Null:
        result2 = self.__parse_list(input);
        if result2 is not Null:
          result3 = self.__parse_whitespace(input);
          if result3 is not Null:
            if ord(self.char(input, self.pos)) == 125:# }
              result4 = '}';
              self.pos += 1;
            else:
              result4 = Null;
              if self.reportFailures == 0:
                self.__matchFailed("'}'");
            if result4 is not Null:
              result0 = [result0, result1, result2, result3, result4];
            else:
              result0 = Null;
              self.pos = pos1;
          else:
            result0 = Null;
            self.pos = pos1;
        else:
          result0 = Null;
          self.pos = pos1;
      else:
        result0 = Null;
        self.pos = pos1;
    else:
      result0 = Null;
      self.pos = pos1;
    if result0 is not Null:
      result0 = result0[2];# Действие
    else:
      self.pos = pos0;
      if input[self.pos:self.pos+4] == 'null':
        result0 = 'null';
        self.pos += 4;
      else:
        result0 = Null;
        if self.reportFailures == 0:
          self.__matchFailed("'null'");

      if result0 is not Null:
        result0 = None;# Действие
      else:
        self.pos = pos0;
      if result0 is Null:
        pos0 = self.pos;
        if input[self.pos:self.pos+4] == 'true':
          result0 = 'true';
          self.pos += 4;
        else:
          result0 = Null;
          if self.reportFailures == 0:
            self.__matchFailed("'true'");
        if result0 is not Null:
          result0 = True;# Действие
        else:
          self.pos = pos0;
          if input[self.pos: self.pos+5] == 'false':
            result0 = 'false';
            self.pos += 5;
          else:
            result0 = Null;
            if self.reportFailures == 0:
              self.__matchFailed("'false'");
          if result0 is not Null:
            result0 = False;# Действие
          else:
            self.pos = pos0;
          if result0 is Null:
            result0 = self.__parse_number(input);
            if result0 is Null:
              result0 = self.__parse_string(input);
    return result0;

  def __parse_list(self, input):
    result0 = result1 = result2 = result3 = result4 = result5 = Null;
    pos0 = pos1 = pos2 = pos3 = Null;

    pos0 = self.pos;
    pos1 = self.pos;
    result0 = self.__parse_value(input);
    if result0 is not Null:
      result1 = self.__parse_whitespace(input);
      if result1 is not Null:
        result2 = [];
        pos2 = self.pos;
        pos3 = self.pos;
        if ord(self.char(input, self.pos)) == 44:# ,
          result3 = ',';
          self.pos += 1;
        else:
          result3 = Null;
          if self.reportFailures == 0:
            self.__matchFailed("','");
        if result3 is not Null:
          result4 = self.__parse_whitespace(input);
          if result4 is not Null:
            result5 = self.__parse_value(input);
            if result5 is not Null:
              result3 = [result3, result4, result5];
            else:
              result3 = Null;
              self.pos = pos3;
          else:
            result3 = Null;
            self.pos = pos3;
        else:
          result3 = Null;
          self.pos = pos3;
        if result3 is not Null:
          result3 = result3[2];# Действие
        if result3 is Null:
          self.pos = pos2;
        while result3 is not Null:
          result2.append(result3);
          pos2 = self.pos;
          pos3 = self.pos;
          if ord(self.char(input, self.pos)) == 44:# ,
            result3 = ',';
            self.pos += 1;
          else:
            result3 = Null;
            if self.reportFailures == 0:
              self.__matchFailed("','");
          if result3 is not Null:
            result4 = self.__parse_whitespace(input);
            if result4 is not Null:
              result5 = self.__parse_value(input);
              if result5 is not Null:
                result3 = [result3, result4, result5];
              else:
                result3 = Null;
                self.pos = pos3;
            else:
              result3 = Null;
              self.pos = pos3;
          else:
            result3 = Null;
            self.pos = pos3;
          if result3 is not Null:
            result3 = result3[2];# Действие
          if result3 is Null:
            self.pos = pos2;
        if result2 is not Null:
          result0 = [result0, result1, result2];
        else:
          result0 = Null;
          self.pos = pos1;
      else:
        result0 = Null;
        self.pos = pos1;
    else:
      result0 = Null;
      self.pos = pos1;
    if result0 is not Null:
      result0[2].insert(0,result0[0]);# Действие
      result0 = result0[2]
    if result0 is Null:
      self.pos = pos0;
    if result0 is Null:
      pos0 = self.pos;
      result0 = [];
    return result0;

  def __parse_string(self, input):
    result0 = result1 = result2 = Null;
    pos0 = pos1 = self.pos;

    if ord(self.char(input, self.pos)) == 34:# "
      result0 = '"';
      self.pos += 1;
    else:
      result0 = Null;
      if self.reportFailures == 0:
        self.__matchFailed("'\"'");
    if result0 is not Null:
      result1 = [];
      result2 = self.__parse_char(input);
      while result2 is not Null:
        result1.append(result2);
        result2 = self.__parse_char(input);
      if result1 is not Null:
        if ord(self.char(input, self.pos)) == 34:
          result2 = '"';
          self.pos += 1;
        else:
          result2 = Null;
          if self.reportFailures == 0:
            self.__matchFailed("'\"'");
        if result2 is not Null:
          result0 = [result0, result1, result2];
        else:
          result0 = Null;
          self.pos = pos1;
      else:
        result0 = Null;
        self.pos = pos1;
    else:
      result0 = Null;
      self.pos = pos1;
    if result0 is not Null:
      result0 = ''.join(result0[1]);# Действие
    if result0 is Null:
      self.pos = pos0;
    return result0;

  def __parse_char(self, input):
    result0 = result1 = Null;
    pos0 = pos1 = Null;
    
    pos0 = self.pos;
    pos1 = self.pos;
    if ord(self.char(input, self.pos)) == 92:# \
      result0 = '\\';
      self.pos += 1;
    else:
      result0 = Null;
      if self.reportFailures == 0:
        self.__matchFailed("'\\\\'");
    if result0 is not Null:
      result1 = self.__parse_hex4(input);
      if result1 is not Null:
        result0 = [result0, result1];
      else:
        result0 = Null;
        self.pos = pos1;
    else:
      result0 = Null;
      self.pos = pos1;
    if result0 is not Null:
      result0 = unichr(result0[1]);# Действие
    if result0 is Null:
      self.pos = pos0;
    if result0 is Null:
      pos0 = self.pos;
      pos1 = self.pos;
      if ord(self.char(input, self.pos)) == 92:
        result0 = '\\';
        self.pos += 1;
      else:
        result0 = Null;
        if self.reportFailures == 0:
          self.__matchFailed("'\\\\'");
      if result0 is not Null:
        if len(input) > self.pos:
          result1 = self.char(input, self.pos);
          self.pos += 1;
        else:
          result1 = Null;
          if self.reportFailures == 0:
            self.__matchFailed("any character");
        if result1 is not Null:
          result0 = [result0, result1];
        else:
          result0 = Null;
          self.pos = pos1;
      else:
        result0 = Null;
        self.pos = pos1;
      if result0 is not Null:
        result0 = result0[1];# Действие
      if result0 is Null:
        self.pos = pos0;
      if result0 is Null:
        if self.rec_char.match(self.char(input, self.pos)):
          result0 = self.char(input, self.pos);
          self.pos += 1;
        else:
          result0 = Null;
          if self.reportFailures == 0:
            self.__matchFailed('[^"]');
    return result0;

  def __parse_hex(self, input):
    result0 = Null;
    
    if self.rec_hex.match(self.char(input, self.pos)):
      result0 = self.char(input, self.pos);
      self.pos += 1;
    else:
      result0 = Null;
      if self.reportFailures == 0:
        self.__matchFailed('[0-9a-fA-F]');
    return result0;

  def __parse_hex4(self, input):
    result0 = result1 = result2 = result3 = Null;
    pos0 = pos1 = self.pos;

    result0 = self.__parse_hex(input);
    if result0 is not Null:
      result1 = self.__parse_hex(input);
      if result1 is not Null:
        result2 = self.__parse_hex(input);
        if result2 is not Null:
          result3 = self.__parse_hex(input);
          if result3 is not Null:
            result0 = [result0, result1, result2, result3];
          else:
            result0 = Null;
            self.pos = pos1;
        else:
          result0 = Null;
          self.pos = pos1;
      else:
        result0 = Null;
        self.pos = pos1;
    else:
      result0 = Null;
      self.pos = pos1;
    if result0 is not Null:
      result0 = int(''.join(result0),16);# Действие
    if result0 is Null:
      self.pos = pos0;
    return result0;

  def __parse_number(self, input):
    result0 = result1 = result2 = Null;
    pos0 = pos1 = self.pos;

    if ord(self.char(input, self.pos)) == 45:# -
      result0 = "-";
      self.pos += 1;
    else:
      result0 = Null;
      if self.reportFailures == 0:
        self.__matchFailed("'-'");
    if result0 is Null:
      result0 = ''
    if result0 is not Null:
      if self.rec_number.match(self.char(input, self.pos)):
        result2 = self.char(input, self.pos);
        self.pos += 1;
      else:
        result2 = Null;
        if self.reportFailures == 0:
          self.__matchFailed('[0-9]');
      if result2 is not Null:
        result1 = [];
        while result2 is not Null:
          result1.append(result2);
          if self.rec_number.match(self.char(input, self.pos)):
            result2 = self.char(input, self.pos);
            self.pos += 1;
          else:
            result2 = Null;
            if self.reportFailures == 0:
              self.__matchFailed('[0-9]');
      else:
        result1 = Null;
      if result1 is not Null:
        result0 = [result0, result1];
      else:
        result0 = Null;
        pos = pos1;
    else:
      result0 = Null;
      pos = pos1;
    if result0 is not Null:
      result0[1].insert(0, result0[0])
      result0 = int(''.join(result0[1]), 10);# Действие
    if result0 is Null:
      pos = pos0;
    return result0;
      

  @staticmethod
  def char(input, index):
    try:
      return input[index];
    except IndexError:
      return '';

  # Обработка ошибок
  def __matchFailed(self, failureMessage):
    if self.pos < self.rightmostFailuresPos:
      return;

    if self.pos > self.rightmostFailuresPos:
      self.rightmostFailuresPos = self.pos;
      self.rightmostFailuresExpected = [];

    self.rightmostFailuresExpected.append(failureMessage);

  @staticmethod
  def __computeErrorPosition(offset, input):
    #
    # The first idea was to use |String.split| to break the input up to the
    # error position along newlines and derive the line and column from
    # there. However IE's |split| implementation is so broken that it was
    # enough to prevent it.
    #

    line = 1;
    column = 1;
    seenCR = False;
    for ch in input[:offset]:
      if ch == '\n':
        if not seenCR:
          line += 1;
        column = 1;
        seenCR = False;
      elif ch == '\r' or ch == '\u2028' or ch == '\u2029':
        line += 1;
        column = 1;
        seenCR = True;
      else:
        column += 1;
        seenCR = False;

    return (line, column);

  @staticmethod
  def __cleanupExpected(expected):
    expected.sort();

    lastExpected = Null;
    cleanExpected = [];
    for e in expected:
      if e != lastExpected:
        cleanExpected.append(e);
        lastExpected = e;
    return cleanExpected;
