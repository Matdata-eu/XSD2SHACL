# SHACL to XSD Mapping Design Rules

This document outlines the design rules and mapping principles applied when converting between SHACL shapes and XSD schemas.

## General Mapping Principles

1. **NodeShape to ComplexType**

   - SHACL Node Shapes are converted to XSD Complex Types
   - The name of the NodeShape becomes the name of the ComplexType

2. **PropertyShape to Element/Attribute**

   - SHACL PropertyShapes are mapped to XSD elements or attributes
   - PropertyShapes with path starting with "@" are mapped to attributes
   - Other PropertyShapes are mapped to elements

3. **Inheritance**

   - SHACL inheritance defined by `sh:node` is mapped to XSD complex type extension
   - If a NodeShape only extends another NodeShape without adding its own properties, the base type is used directly

4. **Constraint Patterns**

   - `sh:or` is mapped to the `<union>` tag for simple types or `<choice>` for complex types
   - `sh:xone` is mapped to the `<choice>` tag
   - `sh:in` with multiple values is mapped to enumeration facets
   - `sh:in` with a single value is mapped to the `fixed` attribute

5. **Container Structure**
   - Since order doesn't matter in SHACL, `<all>` is used instead of `<sequence>` to group elements
   - This better reflects the nature of SHACL as a constraint language rather than a serialization format

## Cardinality Rules

1. **Default Cardinality**

   - Default cardinality constraints (minOccurs="1", maxOccurs="1") are not explicitly included in XSD
   - This produces cleaner XSD with less redundant information

2. **Element Cardinality**

   - `sh:minCount` is mapped to `minOccurs` (only if different from default value 1)
   - `sh:maxCount` is mapped to `maxOccurs` (only if different from default value 1)

3. **Attribute Cardinality**
   - For attributes, `sh:minCount > 0` is mapped to `use="required"`
   - For attributes, `sh:minCount = 0` is mapped to `use="optional"`
   - The default for attributes is `use="optional"`

## Value Constraints

1. **Data Types**

   - SHACL datatypes (`sh:datatype`) are mapped to XSD types
   - Built-in types are used directly (e.g., `xsd:string`, `xsd:integer`)

2. **Numeric Constraints**

   - `sh:minInclusive` → `<minInclusive>`
   - `sh:maxInclusive` → `<maxInclusive>`
   - `sh:minExclusive` → `<minExclusive>`
   - `sh:maxExclusive` → `<maxExclusive>`

3. **String Constraints**

   - `sh:pattern` → `<pattern>`
   - `sh:minLength` → `<minLength>`
   - `sh:maxLength` → `<maxLength>`
   - `sh:length` → `<length>`

4. **Multiple Constraints**
   - When a PropertyShape has multiple constraints (pattern, length, datatype, etc.),
     a simpleType with restriction is created as a child of the element
