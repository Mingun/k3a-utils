# -*- encoding: utf-8 -*-
from __future__ import print_function

import k3a
import argparse

def processCommandLine():
  # Инициализируем парсер:
  parser = argparse.ArgumentParser(
    description=u'Upgrades K3A project when incompatible changes made in TXSST.'
  )
  # Определяем опции:
  parser.add_argument(
    'path',
    help=u'path to directory with K3A project (*.k3a) (may contains environment variables)'
  )
  parser.add_argument(
    'save_path',
    nargs='?',# Необязательный аргумент
    help=u'path when save upgraded K3A configuration'
  )
  parser.add_argument(
    'name',
    nargs='?',# Необязательный аргумент
    help=u'allow set new project name'
  )
  parser.add_argument(
    '-v', '--version',
    action='version',
    version=u'build $WCREV$-$WCMIXED?dev:release$ $WCDATE$',# Версия автоматически заполняется утилитой SubWCRev
    help=u'print version of %(prog)s'
  )
  parser.add_argument(
    '-c', '--check',
    action='store_true',# Необязательная опция
    help=u'make upgrade but do not save upgraded files'
  )
  parser.add_argument(
    '-t', '--show-types',
    dest='types',
    nargs='*',
    help=u'Show K3A objects with specified types (for example, CashDeposit or TxGeneralRequest)'
  )
  parser.add_argument(
    '-n', '--show-names',
    dest='names',
    nargs='*',
    help=u'Show K3A objects with specified names (for example, CashDeposit or TxGeneralRequest)'
  )
  parser.add_argument(
    '-p', '--show-props',
    dest='props',
    nargs='*',
    help=u'Show K3A objects, that has properties with specified names'
  )
  parser.add_argument(
    '-e', '--show-events',
    dest='events',
    nargs='*',
    help=u'Show K3A objects, that has events with specified names'
  )
  parser.add_argument(
    '-d', '--show-docs',
    dest='docs',
    nargs='*',
    help=u'Show K3A objects, that has documents with specified names'
  )

  return parser.parse_args()

def upgrade(project, upgraders):
  def pretty(v):
    v = list(map(str,v))
    v.extend(('x',)*4)
    return '.'.join(v[:4])

  # Кортеж с версией нашей библиотеки
  v = project.versionTXSST()
  print(u'TXSST.dll version: %s' % '.'.join(map(str,v)))
  cnts = (0,0,0)
  for name in sorted(upgraders):
    mod = __import__(name, globals())
    u = mod.Upgrader()
    min = u.minVersion()
    max = u.maxVersion()
    if v < min:
      print(u'SKIP %s: project version lesser then required this upgrade' % name)
      continue
    if v > max:
      print(u'SKIP %s: project version highter then required this upgrade' % name)
      continue
    # Преобразуем версии в читабельную форму major.minor.revision.build
    min = pretty(min)
    max = pretty(max)
    print(u'[%s => %s] Begin upgrade...' % (min, max))
    # Возвращает списки обновленных объектов, списки добавленных/удаленных могут отсутствовать.
    r = u.upgrade(project)
    # Увеличиваем длину кортежа до 3-х.
    r = tuple(map(len, r+(((),)*3))[:3])
    cnts = map(sum, zip(r, cnts))
    print(u'[%s => %s] complete! Objects upgraded/added/removed: %d/%d/%d' % ((min, max)+r))
  print()
  print(u'All upgrades completed! Objects upgraded/added/removed: %d/%d/%d' % tuple(cnts))

def showInfo(project, args, f=print):
  def helper(filter, prop):
    if filter:
      print('~'*80);
      print(u'Objects with %s: %s' % (prop, ', '.join(filter)));
      print('~'*80);
      candidates = [];
      for x in filter:
        for o in project.objects():
          if x in (p.name for p in o[prop]):
            candidates.add(x);
      for o in unique(candidates):
        f(o);
  if args.types:
    print('~'*80);
    print(u'Objects with types: %s' % ', '.join(args.types));
    print('~'*80);
    for x in args.types:
      for o in project.objects():
        if o.type == x:
          f(o);
  if args.names:
    print('~'*80);
    print(u'Objects with names: %s' % ', '.join(args.names));
    print('~'*80);
    for x in args.names:
      for o in project.objects():
        if o.name == x:
          f(o);
  helper(args.props, 'props');
  helper(args.events, 'events');
  helper(args.docs, 'docs');

  # Если задан хотя бы один из параметров без аргументов, то выводим список всех объектов.
  if args.types is not None and len(args.types) == 0 \
  or args.names is not None and len(args.names) == 0 \
  or args.props is not None and len(args.props) == 0 \
  or args.events is not None and len(args.events) == 0 \
  or args.docs is not None and len(args.docs) == 0:
    print('~'*80);
    print(u'All objects:');
    print('~'*80);
    for o in project.objects():
      f(o);
  

if __name__ == "__main__":
  # @type project k3a.K3AProject
  upgraders = (
    'upgrade-0_2_x_x-0_3_x_x',
  )
  args = processCommandLine();
  project = k3a.K3AProject(args.path);
  showInfo(project, args, lambda o: o.dump());

  upgrade(project, upgraders);

  if args.save_path:
    project.dir = args.save_path;
  if args.name:
    project.name = args.name;
  project.dir = 'Copy'
  if args.check:
    print();
    print(u'Not save upgraded project because `--check` option was specified');
  else:
    project.save(True);