import xml.etree.ElementTree as ET
import os
import rdflib
from rdflib import Graph, Literal, BNode, Namespace, RDF, URIRef
import time
from .utils import built_in_types


class SHACLtoXSD:
    def __init__(self):
        """
        Initialize the SHACLtoXSD class
        """
        self.shaclNS = rdflib.Namespace('http://www.w3.org/ns/shacl#')
        self.rdfSyntax = rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
        self.xsdNS = rdflib.Namespace('http://www.w3.org/2001/XMLSchema#')
        self.xsdTargetNS = rdflib.Namespace('http://example.com/')
        self.NS = rdflib.Namespace('http://example.com/')
        self.type_list = built_in_types()
        
        self.SHACL = Graph()
        self.processed_shapes = set()
        self.xsd_root = None
        self.xsd_nsmap = {
            'xs': 'http://www.w3.org/2001/XMLSchema',
            'tns': 'http://example.com/'
        }
        
        self.ns_prefix_map = {}
        self.node_shape_map = {}  # Maps NodeShape URIs to XSD complexType elements
        self.property_shape_map = {}  # Maps PropertyShape URIs to XSD element/attribute elements
        self.use_xsd_prefix = False  # Flag to determine whether to use 'xs' or 'xsd' namespace prefix
        
    def create_xsd_root(self):
        """
        Create the root element for the XSD document
        """
        # Register namespaces for proper prefix use
        for prefix, uri in self.ns_prefix_map.items():
            ET.register_namespace(prefix, uri)
            
        # Create the root element with proper namespace
        self.xsd_root = ET.Element("{http://www.w3.org/2001/XMLSchema}schema")
        
        # Check if xsd prefix is used in the SHACL input
        self.use_xsd_prefix = 'xsd' in self.ns_prefix_map and self.ns_prefix_map['xsd'] == 'http://www.w3.org/2001/XMLSchema'
        
        # Set the XML namespace prefix for schema elements based on detected prefix
        schema_prefix = 'xsd' if self.use_xsd_prefix else 'xs'
        self.xsd_root.set(f"xmlns:{schema_prefix}", "http://www.w3.org/2001/XMLSchema")
        
        # Add other namespace declarations
        for prefix, uri in self.xsd_nsmap.items():
            if prefix != 'xs' and prefix != 'xsd':  # Skip both xs and xsd as we handle them separately
                self.xsd_root.set(f"xmlns:{prefix}", uri)
        
        # Only set these attributes if they're not already set by the namespace declarations
        self.xsd_root.set("targetNamespace", str(self.xsdTargetNS))
        self.xsd_root.set("elementFormDefault", "qualified")
        self.xsd_root.set("attributeFormDefault", "unqualified")

    def get_shape_name(self, shape_uri):
        """
        Get the name of a shape
        """
        name_literal = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.name)
        if name_literal:
            return str(name_literal)
        
        # If no name is available, extract it from the URI
        uri_str = str(shape_uri)
        if 'NodeShape/' in uri_str:
            return uri_str.split('NodeShape/')[-1]
        elif 'PropertyShape/' in uri_str:
            path = uri_str.split('PropertyShape/')[-1]
            if path.startswith('@'):
                return path[1:]  # Remove @ for attributes
            return path
        
        # Fallback to the last part of the URI
        return uri_str.split('/')[-1]
    
    def process_node_shape(self, shape_uri):
        """
        Process a SHACL NodeShape and convert it to XSD complexType
        """
        # Skip if already processed
        if shape_uri in self.processed_shapes:
            return self.node_shape_map.get(shape_uri)
            
        self.processed_shapes.add(shape_uri)
        
        # Get the shape name
        shape_name = self.get_shape_name(shape_uri)
        
        # Create the complexType element
        prefix = 'xsd' if self.use_xsd_prefix else 'xs'
        complex_type = ET.Element(f"{{{self.xsd_nsmap['xs']}}}complexType")
        complex_type.set("name", shape_name)
        
        # Process sh:node - to handle inheritance through extension
        node_values = list(self.SHACL.objects(subject=shape_uri, predicate=self.shaclNS.node))
        extension = None
        
        if node_values:
            base_shape_uri = node_values[0]
            base_complex_type = self.process_node_shape(base_shape_uri)
            if base_complex_type is not None:
                # Create extension base for inheritance
                complex_content = ET.SubElement(complex_type, f"{{{self.xsd_nsmap['xs']}}}complexContent")
                extension = ET.SubElement(complex_content, f"{{{self.xsd_nsmap['xs']}}}extension")
                extension.set("base", self.get_shape_name(base_shape_uri))
        
        # Check for sh:xone (which maps to <choice>)
        xone_nodes = list(self.SHACL.objects(subject=shape_uri, predicate=self.shaclNS.xone))
        if xone_nodes:
            container = extension if extension is not None else complex_type
            # Process the xone list which contains references to property shapes
            self.process_choice_constraint(xone_nodes[0], container, is_xone=True)
        
        # Check for sh:or (which maps to <union>)
        or_nodes = list(self.SHACL.objects(subject=shape_uri, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#or')))
        if or_nodes:
            container = extension if extension is not None else complex_type
            self.process_choice_constraint(or_nodes[0], container, is_xone=False)
            
        # Process properties (sh:property)
        property_nodes = list(self.SHACL.objects(subject=shape_uri, predicate=self.shaclNS.property))
        
        if property_nodes:
            # Create all or add directly to extension
            container = extension if extension is not None else complex_type
            
            # We'll add elements to an "all" group unless we're using a choice
            # This reflects that order doesn't matter in SHACL
            if not xone_nodes and not or_nodes:
                all_group = ET.SubElement(container, f"{{{self.xsd_nsmap['xs']}}}all")
                container = all_group
            
            # Process each property
            for prop in property_nodes:
                prop_elem = self.process_property_shape(prop)
                if prop_elem is not None:
                    if prop_elem.tag.endswith('element'):
                        container.append(prop_elem)
                    elif prop_elem.tag.endswith('attribute'):
                        complex_type.append(prop_elem)
        
        # Remember this node shape
        self.node_shape_map[shape_uri] = complex_type
        
        # Check if this shape has a targetClass (meaning it should be a top-level element)
        target_classes = list(self.SHACL.objects(subject=shape_uri, predicate=self.shaclNS.targetClass))
        if target_classes:
            # Create a top-level element that references this complex type
            for target_class in target_classes:
                element = ET.Element(f"{{{self.xsd_nsmap['xs']}}}element")
                element.set("name", self.get_shape_name(shape_uri))
                
                # Check if this complex type only extends another type without adding properties
                if (extension is not None and 
                    all(child.tag.endswith('complexContent') for child in complex_type) and
                    not list(self.SHACL.objects(subject=shape_uri, predicate=self.shaclNS.property))):
                    # Use the base type directly instead
                    base_type_name = extension.get("base")
                    element.set("type", base_type_name)
                else:
                    element.set("type", shape_name)
                    
                self.xsd_root.append(element)
        
        # Add the complex type to the root
        self.xsd_root.append(complex_type)
        return complex_type
    
    def process_choice_constraint(self, list_node, parent_element, is_xone=True):
        """
        Process a sh:xone or sh:or constraint and convert it to choice or union
        """
        # For sh:xone, create a <choice> element
        if is_xone:
            choice = ET.SubElement(parent_element, f"{{{self.xsd_nsmap['xs']}}}choice")
            self.process_rdf_list(list_node, choice)
        # For sh:or, decide whether to use union or complexContent with extension
        else:
            # Check if we're dealing with simple types or complex types
            items = self.get_rdf_list_items(list_node)
            # If dealing with simple types, use union
            if self.are_simple_type_constraints(items):
                # Create a simpleType with union
                simple_type = ET.SubElement(parent_element, f"{{{self.xsd_nsmap['xs']}}}simpleType")
                union = ET.SubElement(simple_type, f"{{{self.xsd_nsmap['xs']}}}union")
                # Add memberTypes
                member_types = []
                for item in items:
                    datatype = self.SHACL.value(subject=item, predicate=self.shaclNS.datatype)
                    if datatype:
                        member_types.append(str(datatype).split('#')[-1])
                union.set("memberTypes", " ".join(member_types))
            # If dealing with complex types, use choice
            else:
                choice = ET.SubElement(parent_element, f"{{{self.xsd_nsmap['xs']}}}choice")
                self.process_rdf_list(list_node, choice)
    
    def are_simple_type_constraints(self, item_list):
        """
        Check if the items in an sh:or constraint are all simple types
        """
        for item in item_list:
            # Check if this is a simple type constraint (has datatype, pattern, etc.)
            datatype = self.SHACL.value(subject=item, predicate=self.shaclNS.datatype)
            if not datatype:
                return False
        return True
    
    def get_rdf_list_items(self, list_node):
        """
        Extract items from an RDF list
        """
        items = []
        while list_node != RDF.nil:
            item = self.SHACL.value(subject=list_node, predicate=RDF.first)
            if item:
                items.append(item)
            list_node = self.SHACL.value(subject=list_node, predicate=RDF.rest)
            if not list_node:
                break
        return items
    
    def process_rdf_list(self, list_node, parent_element):
        """
        Process an RDF list and add its items to the parent element
        """
        items = self.get_rdf_list_items(list_node)
        
        for item in items:
            # Check if this is a PropertyShape or a NodeShape
            is_property = (item, RDF.type, self.shaclNS.PropertyShape) in self.SHACL
            
            if is_property:
                prop_elem = self.process_property_shape(item)
                if prop_elem is not None:
                    parent_element.append(prop_elem)
            else:
                # Could be a reference to a NodeShape, handle accordingly
                node_elem = self.process_node_shape(item)
                if node_elem is not None:
                    # Create a reference to the node shape
                    ref_elem = ET.Element(f"{{{self.xsd_nsmap['xs']}}}element")
                    ref_elem.set("ref", self.get_shape_name(item))
                    parent_element.append(ref_elem)
    
    def process_property_shape(self, shape_uri):
        """
        Process a SHACL PropertyShape and convert it to XSD element, attribute or simpletype
        """
        # Skip if already processed
        if shape_uri in self.processed_shapes:
            return self.property_shape_map.get(shape_uri)
            
        self.processed_shapes.add(shape_uri)
        
        # Get the shape name
        shape_name = self.get_shape_name(shape_uri)
        
        # Determine if this is an attribute or element
        is_attribute = '@' in str(shape_uri) or shape_name.startswith('@')
        
        # Clean the name if it's an attribute (remove leading @)
        if is_attribute and shape_name.startswith('@'):
            shape_name = shape_name[1:]
                
        # Get the path of the property
        path = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.path)
        if not path:
            # No path defined, can't create element/attribute
            return None
        
        # Create the element or attribute
        prefix = 'xsd' if self.use_xsd_prefix else 'xs'
        element_type = 'attribute' if is_attribute else 'element'
        element = ET.Element(f"{{{self.xsd_nsmap['xs']}}}{element_type}")
        element.set("name", shape_name)
        
        # Check for sh:or (which maps to <union> for property shapes)
        or_nodes = list(self.SHACL.objects(subject=shape_uri, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#or')))
        if or_nodes and not is_attribute:  # or constraints don't apply to attributes
            or_node = or_nodes[0]
            # Create a simpleType with union
            simple_type = ET.SubElement(element, f"{{{self.xsd_nsmap['xs']}}}simpleType")
            
            # Get the items in the sh:or list
            items = self.get_rdf_list_items(or_node)
            
            # If these are datatype constraints, create a union
            if self.are_simple_type_constraints(items):
                union = ET.SubElement(simple_type, f"{{{self.xsd_nsmap['xs']}}}union")
                member_types = []
                for item in items:
                    datatype = self.SHACL.value(subject=item, predicate=self.shaclNS.datatype)
                    if datatype:
                        member_types.append(str(datatype).split('#')[-1])
                union.set("memberTypes", " ".join(member_types))
            # Otherwise, create a choice structure
            else:
                # For complex choices, might need more complex handling
                # This is a simplified approach that might need refinement
                restriction = ET.SubElement(simple_type, f"{{{self.xsd_nsmap['xs']}}}restriction")
                restriction.set("base", "string")  # Default base
                
                # Note: For complex sh:or constraints in property shapes,
                # a more sophisticated approach might be needed
            
            # Remove any existing type attribute
            if "type" in element.attrib:
                del element.attrib["type"]
                
            # Since we've handled or constraints already, return the element
            self.property_shape_map[shape_uri] = element
            return element
        
        # Process data type
        datatype = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.datatype)
        if datatype:
            # Map the datatype from SHACL to XSD
            xsd_type = str(datatype).split('#')[-1]
            element.set("type", xsd_type)
        
        # Process cardinality constraints
        min_count = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.minCount)
        if min_count is not None:
            if is_attribute:
                # For attributes, use=required if minCount > 0
                if int(min_count) > 0:
                    element.set("use", "required")
                else:
                    element.set("use", "optional")
            else:
                # Only add minOccurs if it's not the default (1)
                if str(min_count) != "1":
                    element.set("minOccurs", str(min_count))
        elif is_attribute:
            # Default for attributes is optional
            element.set("use", "optional")
            
        max_count = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.maxCount)
        if max_count is not None and not is_attribute:
            # Only add maxOccurs if it's not the default (1)
            if str(max_count) != "1":
                element.set("maxOccurs", str(max_count))
            
        # Process value list constraints
        self.process_list_constraints(shape_uri, element)
        
        # Process numeric constraints 
        self.process_facet_constraints(shape_uri, element)
                
        # Remember this property shape
        self.property_shape_map[shape_uri] = element
        return element
    
    def process_list_constraints(self, shape_uri, element):
        """
        Process value constraints from SHACL to XSD
        """
        # Process enumeration (sh:in)
        in_values = list(self.SHACL.objects(subject=shape_uri, predicate=self.shaclNS['in']))
        if in_values:
            # Get the first (and should be only) in_value
            in_value = in_values[0]
            
            # Check if this is an RDF list
            if (in_value, RDF.first, None) in self.SHACL:
                # This is an RDF list of allowed values (enumeration)
                values = self.get_rdf_list_items(in_value)
                
                # If the list has only one value, use fixed attribute instead of enumeration
                if len(values) == 1:
                    element.set("fixed", str(values[0]))
                    
                    # Remove the type attribute if we're defining it inline
                    if "type" in element.attrib:
                        del element.attrib["type"]
                    return
                    
                # Create simpleType with restriction for enumeration
                prefix = 'xsd' if self.use_xsd_prefix else 'xs'
                
                # Determine the base type based on the datatype of the property
                base_type = "string"  # Default
                datatype = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.datatype)
                if datatype:
                    base_type = str(datatype).split('#')[-1]
                
                # Only create restriction if we have values
                if values:
                    # Create the simple type structure
                    simple_type = ET.SubElement(element, f"{{{self.xsd_nsmap['xs']}}}simpleType")
                    restriction = ET.SubElement(simple_type, f"{{{self.xsd_nsmap['xs']}}}restriction")
                    restriction.set("base", base_type)
                    
                    # Add enumeration facets
                    for value in values:
                        enum = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}enumeration")
                        enum.set("value", str(value))
                    
                    # Remove the type attribute since we're defining it inline
                    if "type" in element.attrib:
                        del element.attrib["type"]
            elif in_values[0] == RDF.nil:
                # Empty list, no constraints
                pass
            else:
                # This might be a single fixed value
                # Set as fixed attribute if appropriate
                element.set("fixed", str(in_values[0]))
    
    def process_facet_constraints(self, shape_uri, element):
        """
        Process numeric constraints from SHACL to XSD
        """
        # Check if we need to create a simpleType with restrictions
        needs_restriction = False
        
        # Process pattern constraint
        pattern = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.pattern)
        
        # Get the datatype
        datatype = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.datatype)
        base_type = "decimal"  # Default for numeric values
        if datatype:
            base_type = str(datatype).split('#')[-1]
            
        # Check for numeric constraints
        min_exclusive = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.minExclusive)
        max_exclusive = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.maxExclusive)
        min_inclusive = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.minInclusive)
        max_inclusive = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.maxInclusive)
        
        # Check if we need to create a restriction
        if min_exclusive is not None or max_exclusive is not None or min_inclusive is not None or max_inclusive is not None:
            needs_restriction = True
        
        # Also check for length constraints
        min_length = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.minLength)
        max_length = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.maxLength)
        exact_length = self.SHACL.value(subject=shape_uri, predicate=self.shaclNS.length)
        
        if not (pattern or min_length is not None or max_length is not None or exact_length is not None):
            # no restrictions needed, return early
            return
            
        # If element already has a simpleType child, use that
        simple_type = None
        for child in element:
            if child.tag.endswith('simpleType'):
                simple_type = child
                break
                
        if simple_type is None:
            simple_type = ET.SubElement(element, f"{{{self.xsd_nsmap['xs']}}}simpleType")
            
        # Find or create the restriction element
        restriction = None
        for child in simple_type:
            if child.tag.endswith('restriction'):
                restriction = child
                break
                
        if restriction is None:
            restriction = ET.SubElement(simple_type, f"{{{self.xsd_nsmap['xs']}}}restriction")
            restriction.set("base", base_type)
            
            # Remove the type attribute as we're defining it inline
            if "type" in element.attrib:
                del element.attrib["type"]
        
        # Add pattern facet if present
        if pattern:
            pattern_elem = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}pattern")
            pattern_elem.set("value", str(pattern))
        
        # Add numeric facets
        if min_exclusive is not None:
            facet = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}minExclusive")
            facet.set("value", str(min_exclusive))
            
        if max_exclusive is not None:
            facet = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}maxExclusive")
            facet.set("value", str(max_exclusive))
            
        if min_inclusive is not None:
            facet = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}minInclusive")
            facet.set("value", str(min_inclusive))
            
        if max_inclusive is not None:
            facet = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}maxInclusive")
            facet.set("value", str(max_inclusive))
            
        # Add length facets
        # If min_length==max_length and exact_length is not None, we can use one of these as exact_length
        # Set exact_length if min_length equals max_length
        if exact_length is None and min_length is not None and max_length is not None and min_length == max_length:
            exact_length = min_length

        if exact_length is not None :
            facet = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}length")
            facet.set("value", str(exact_length))
            
        else :
            if min_length is not None:
                facet = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}minLength")
                facet.set("value", str(min_length))
            
            if max_length is not None:
                facet = ET.SubElement(restriction, f"{{{self.xsd_nsmap['xs']}}}maxLength")
                facet.set("value", str(max_length))
    
        # Remove the type attribute since we're defining it inline
        # if "type" in element.attrib:
        #     del element.attrib["type"]

    def convert(self):
        """
        Convert SHACL shapes to XSD
        """
        # Create XSD root
        self.create_xsd_root()
                
        # Find all node shapes
        node_shapes = list(self.SHACL.subjects(predicate=RDF.type, object=self.shaclNS.NodeShape))
        
        # Process each node shape
        for node_shape in node_shapes:
            self.process_node_shape(node_shape)
                    
        # Find all property shapes that are not processed yet (standalone/top-level property shapes)
        all_property_shapes = list(self.SHACL.subjects(predicate=RDF.type, object=self.shaclNS.PropertyShape))
        unprocessed_property_shapes = [ps for ps in all_property_shapes if ps not in self.processed_shapes]
        
        # Process each standalone property shape as top-level elements
        for property_shape in unprocessed_property_shapes:
            property_element = self.process_property_shape(property_shape)
            if property_element is not None:
                # Only add direct children to the root if they're elements, not attributes
                if property_element.tag.endswith('element'):
                    self.xsd_root.append(property_element)
            
        # Create the ElementTree
        self.xsdTree = ET.ElementTree(self.xsd_root)
    
    def load_shacl_file(self, shacl_file):
        """
        Load SHACL file into the graph
        """
        self.SHACL.parse(shacl_file, format="turtle")
        
        # Extract namespace prefix mappings
        for prefix, namespace in self.SHACL.namespaces():
            self.ns_prefix_map[prefix] = namespace
            
            # Check if there's an XSD namespace prefix defined and remember it
            if str(namespace) == 'http://www.w3.org/2001/XMLSchema#':
                self.use_xsd_prefix = (prefix == 'xsd')
            
        # Extract target namespace
        for s, p, o in self.SHACL.triples((None, self.shaclNS.targetClass, None)):
            if o and isinstance(o, URIRef):
                ns = str(o).rsplit('/', 1)[0] + '/'
                self.xsdTargetNS = rdflib.Namespace(ns)
                self.NS = rdflib.Namespace(ns)
                self.xsd_nsmap['tns'] = ns
                break
                
    def write_xsd_to_file(self, output_file):
        """
        Write the XSD to file
        """
        # Register namespaces for cleaner XML output
        for prefix, uri in self.ns_prefix_map.items():
            if prefix not in ['xs', 'xsd']:  # Skip standard XSD namespaces to avoid conflicts
                ET.register_namespace(prefix, uri)
        
        # Register standard namespaces
        schema_prefix = 'xsd' if self.use_xsd_prefix else 'xs'
        ET.register_namespace(schema_prefix, 'http://www.w3.org/2001/XMLSchema')
        ET.register_namespace('', 'http://www.w3.org/2001/XMLSchema')
            
        try:
            # Use ElementTree's built-in pretty printing for XML output
            indent(self.xsd_root)  # Add indentation for pretty printing
            
            # Write directly to file using ElementTree
            tree = ET.ElementTree(self.xsd_root)
            tree.write(output_file, encoding='utf-8', xml_declaration=True)
            return output_file
        except Exception as e:
            print(f"Error using ElementTree to write XML: {e}")
            
            # Fallback to minidom if ElementTree fails
            try:
                rough_string = ET.tostring(self.xsd_root, encoding='utf-8')
                
                # Remove any duplicate namespace declarations before parsing
                from xml.dom import minidom
                reparsed = minidom.parseString(rough_string)
                pretty_xml = reparsed.toprettyxml(indent="  ")
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(pretty_xml)
                    
                return output_file
            except Exception as nested_e:
                print(f"Error using minidom to write XML: {nested_e}")
                raise
    
    def shacl_to_xsd(self, shacl_file, output_file=None):
        """
        Main method to convert SHACL to XSD
        """
        # print("Loading SHACL file...")
        self.load_shacl_file(shacl_file)
        
        # print("Converting SHACL to XSD...")
        start = time.time()
        self.convert()
        end = time.time()
        # print("Conversion time: " + str(end - start), "seconds")
        
        if output_file is None:
            output_file = shacl_file + ".xsd"
            
        # print("Writing XSD to file...")
        self.write_xsd_to_file(output_file)
        # print(f"XSD file written to {output_file}")
        
        return output_file

# Helper function for XML pretty printing
def indent(elem, level=0):
    """
    Add indentation to make the XML output more readable
    """
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i