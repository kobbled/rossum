import collections
from typing import NamedTuple

class Packages(NamedTuple):
  name: str
  version: str
  inSource: str

#Class to represent a graph 
class graph:
  def __init__(self, root=None, version=None): 
      self.graph = collections.defaultdict(list) #dictionary containing adjacency List
      self.root = []
      if root is not None and version is not None:
          self.root.append(self.addPackage(root, version, True))

  def __getitem__(self, key):
      for next in self.root:
          if next.name == key:
              return next

  def print_dependencies(self, rootname):
      depList = ''
      
      stack = self.depthFirstSearch(rootname)
      depList += '<{}> {} {x}\n'.format(rootname, self[rootname].version, x='*' if self[rootname].inSource else '')
      stack.remove(rootname)

      for next in self.graph[rootname]:
          depList = self.depPrintRec(next, stack, '|-- ', depList)

      return depList

  def depPrintRec(self, pkg, stack, prepStr, outstr):
      if pkg.name in stack:
          outstr += prepStr + '<{}> {} {x}\n'.format(pkg.name, pkg.version, x='*' if pkg.inSource else '')
          stack.remove(pkg.name)

      for next in self.graph[pkg.name]:
          if next.name in stack:
              outstr = self.depPrintRec(next, stack, '|   ' + prepStr, outstr)

      return outstr


  def addPackage(self, Name, Version, Source):
      return Packages(
              name= Name,
              version= Version,
              inSource= Source)

  def setRoot(self, name, version):
      self.root.append(self.addPackage(name, version, True))

  # function to add an edge to graph 
  def addEdge(self, pNode, cNode, version, isSource):
      self.graph[pNode].append(self.addPackage(cNode, version, isSource))

  def depthFirstSearch(self, start, visited=None, stack=None):
      if visited is None:
          visited = set()
      if stack is None:
          stack = []
          
      stack.append(start)
      visited.add(start)
      
      pkg_names = set([p.name for p in self.graph[start]])

      difference = pkg_names - visited
      for next in difference:
          self.depthFirstSearch(next,visited, stack)
      
      return stack