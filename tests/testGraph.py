from graph.graph import graph
import unittest

class testGraph(unittest.TestCase):
  def test(self):
    g= graph()
    g.setRoot("Hash", '1.0.0')
    g.addEdge("Hash", "kUnit", '0.0.1', True)
    g.addEdge("Hash", "Strings", '0.0.2', True)
    g.addEdge("Strings", "errors", '0.0.3', False) 
    g.addEdge("Strings", "kUnit", '0.0.4', True)
    g.addEdge("kUnit", "Strings", '0.0.2', True)
    g.addEdge("errors", "registers", '0.0.1', False)
    g.addEdge("errors", "kUnit", '0.0.4', True)

    g.setRoot("ioFile", '1.0.0')
    g.addEdge("ioFile", "Strings", '0.0.2', True)

    self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()