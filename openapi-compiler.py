#!/usr/bin/python

import yaml
import json
import os
import sys

class PropertyDef:
    def __init__( self, name, type_def ):
        """
        Args:
            name - string
            type_def - TypeDef object
        """
        self.name = name
        self.type_def = type_def

    def get_name( self ):
        return self.name

    def get_type( self ):
        return self.type_def.get_name()

    def is_array( self ):
        return self.type_def.is_array()


class Field:
    def __init__( self, name, type, required = False, fixed_value = None, array = False ):
        self.name = name
        self.type = type
        self.required = required
        self.fixed_value = fixed_value
        self.array = array

    def get_name( self ):
        return self.name

    def get_type( self ):
        return self.type

    def is_required( self ):
        return self.required

    def is_fixed( self ):
        return self.fixed_value is not None

    def get_fixed_value( self ):
        return self.fixed_value

    def is_array( self ):
        return self.array


class TypeDef:
    def __init__( self, path, type_def, openapi ):
        self.path = path
        self.type_def = type_def
        self.openapi = openapi


    def get_parent( self ):
        """
        get the parent type
        """
        return None

    def get_type( self ):
        if 'type' in self.type_def:
            return self.type_def['type']
        elif '$ref' in self.type_def:
            return '$ref'
        elif 'oneOf' in self.type_def:
            return 'oneOf'
        elif 'allOf' in self.type_def:
            return 'allOf'
        elif "anyOf" in self.type_def:
            return "anyOf"
        elif "array" in self.type_def:
            return "array"
        else:
            return None

    def get_path( self ):
        return self.path

    def get_discriminator_mapping( self ):
        return None, None

    def get_name( self ):
        """
        get the type name
        """
        if len( self.path ) > 0:
            return filter( lambda x: len( x ) > 0, self.path.split( '/' ) ) [-1]
        elif 'type' in self.type_def:
            return self.type_def['type']
        return None

    def is_type( self, type_name ):
        return self.get_type() == type_name

    def is_ref_type( self ):
        """
        check if it is reference type
        """
        return self.get_type() == "$ref"

    def is_basic_type( self ):
        basic_types = ["string", "integer", "number"]
        return self.get_type() in basic_types

    def get_ref_type( self ):
        return self.openapi.get_ref_type( self.type_def['$ref'] ) if '$ref' in self.type_def else None

    def is_oneOf( self ):
        return self.is_type( 'oneOf' )

    def is_allOf( self ):
        return self.is_type( 'allOf' )

    def is_anyOf( self ):
        return self.is_type( "anyOf" )

    def is_object( self ):
        return self.is_type( 'object' )

    def is_array( self ):
        return self.is_type( "array" )

    def get_enum_values( self ):
        return self.type_def['enum'] if 'enum' in self.type_def else None

    def is_enum( self ):
        return 'enum' in self.type_def

    def __repr__( self ):
        return json.dumps( self.type_def )

class ObjectType( TypeDef ):
    def __init__( self, path, type_def, openapi ):
        TypeDef.__init__( self, path, type_def, openapi )

    def get_required( self ):
        return self.type_def['required'] if 'required' in self.type_def else []

    def get_properties( self ):
        """
        get properties if type is object

        Return: list of PropertyDef
        """
        result = []
        if 'properties' in self.type_def:
            props = self.type_def['properties']
            for prop_name in  props:
                prop = props[ prop_name ]
                if isinstance( prop, dict ) and '$ref' in prop:
                     result.append( PropertyDef( prop_name, self.openapi.get_ref_type( prop["$ref"] ) ) )
                else:
                     result.append( PropertyDef( prop_name, TypeFactory.create_type( "", prop, self.openapi ) ) )
        return result

    def get_fields( self ):
        """
        get fields defined in the object
        """
        fields = []
        required_fields = self.get_required()
        for prop in self.get_properties():
            required = prop.get_name() in required_fields
            fields.append( Field( prop.get_name(), prop.get_type(), required = required, array = prop.is_array() ) )
        return fields

    def has_discriminator( self ):
        return 'discriminator' in self.type_def

    def get_discriminator_field( self ):
        return self.type_def['discriminator']['propertyName']

    def get_discriminator_mapping( self, ref ):
        """
        return: a tuple of ( discriminator_field, mapping_value )
        """
        if not self.has_discriminator():
            return None, None
        discriminator_field = self.get_discriminator_field()
        mapping = self.type_def['discriminator']['mapping']
        for m in mapping:
            if mapping[m] == ref:
                return discriminator_field, m

        return None, None

class BasicType( TypeDef ):
    def __init__( self, path, type_def, openapi ):
        TypeDef.__init__( self, path, type_def, openapi )

    def get_name( self ):
        type_name = self.type_def['type'] if 'type' in self.type_def else 'string'
        type_format = self.type_def['format'] if 'format' in self.type_def else None
        real_type_mapper = { "int32@integer": "int32",
                             "int64@integer": "int64",
                             "None@integer": "int64",
                             "integer": "int64",
                             "float@number": "float",
                             "double@number": "double",
                             "number": "double",
                             "date@string": "date",
                             "date-time@string": "date-time",
                             "string": "string" }

        t = "%s@%s" % ( type_format, type_name )
        return real_type_mapper[t] if t in real_type_mapper else type_name

    def is_nullable( self ):
        return self.type_def['nullable'] if 'nullable' in self.type_def else False



class OneOfType( TypeDef ):
    def __init__( self, path, type_def, openapi ):
        TypeDef.__init__( self, path, type_def, openapi )

    def is_oneOf( self ):
        return True

    def get_all_types( self ):
        """
        get all the types defined in the oneOf
        """
        types = []
        for t in self.type_def['oneOf']:
            if '$ref' in t:
                types.append( self.openapi.get_ref_type( t['$ref'] ) )
            else:
                types.append( TypeFactory.create_type( "", t, self.openapi ) )
        return types


class AnyOfType( TypeDef ):
    def __init__( self, path, type_def, openapi ):
        TypeDef.__init__( self, path, type_def, openapi )

    def is_anyOf( self ):
        return True

    def get_all_types( self ):
        """
        get all the types defined in the anyOf
        """
        types = []
        for t in self.type_def['anyOf']:
            if '$ref' in t:
                types.append( self.openapi.get_ref_type( t['$ref'] ) )
            else:
                types.append( TypeFactory.create_type( "", t, self.openapi ) )
        return types


class AllOfType( TypeDef ):
     def __init__( self, path, type_def, openapi ):
        TypeDef.__init__( self, path, type_def, openapi )

     def is_allOf( self ):
         return True

     def get_parent( self ):
         return self.get_ref_type().get_name()

     def get_type( self ):
         for item in self.type_def["allOf"]:
             if "type" in item:
                 return TypeFactory.create_type( "", item, self.openapi )
         return None

     def get_ref_type( self ):
         for item in self.type_def['allOf']:
             if '$ref' in item:
                 return self.openapi.get_ref_type( item['$ref'] )
         return None

     def get_fields( self ):
         required_fields = self.get_type().get_required()
         fields = self.get_type().get_fields()
         #fields.extend( self.get_ref_type().get_fields() )
         return fields

class ArrayType( TypeDef ):
    def __init__( self, path, type_def, openapi ):
        TypeDef.__init__( self, path, type_def, openapi )

    def get_name( self ):
        items = self.type_def['items']
        if "$ref" in items:
            return self.openapi.get_ref_type( items["$ref"] ).get_name()
        else:
            return TypeFactory.create_type( "", self.type_def['items'], self.openapi ).get_name()


class RefType( TypeDef ):
     def __init__( self, path, type_def, openapi ):
         TypeDef.__init__( self, path, type_def, openapi )

     def get_type( self ):
         return "unknown"

     def get_fields( self ):
         return self.openapi.get_ref_type( self.type_def['$ref'] ).get_fields()



class TypeFactory:
    @classmethod
    def create_type( cls, path, type_def, openapi ):
        if "type" in type_def:
            if "object" == type_def["type"]:
                return ObjectType( path, type_def, openapi )
            elif "array" == type_def["type"]:
                return ArrayType( path, type_def, openapi )
            else:
                return BasicType( path, type_def, openapi )
        elif "allOf" in type_def:
            return AllOfType( path, type_def, openapi )
        elif "anyOf" in type_def:
            return AnyOfType( path, type_def, openapi )
        elif "oneOf" in type_def:
            return OneOfType( path, type_def, openapi )
        elif "$ref" in type_def:
            return RefType( path, type_def, openapi )
        elif "type" not in type_def:
            return BasicType( path, type_def, openapi )
        else:
            print type_def
            raise Exception( "unkown type definition" )

class OpenapiDef:
    def __init__( self, api_def):
        self.api_def = api_def
        #other openapi definition files
        self.files = {}

    def get_ref_type( self, ref_type ):
        """
        get the underline reference type, the refence type must be one of following like:
            #/components/schemas/MyType
            other.yaml##/components/schemas/OtherType
        return:
            a TypeDef object
        """
        pos = ref_type.find( '#' )
        if pos == 0:
            return self.get_type( ref_type[1:] )
        elif pos > 0:
            return self._load_file( ref_type[0:pos].strip() ).get_ref_type( ref_type[pos:] )
        else:
            return None


    def get_type( self, path ):
        type_def = self.get_def( path )
        return TypeFactory.create_type( path, type_def, self ) if type_def is not None else None

    def get_def( self, path ):
        """
        get definition by path
        """
        elements = filter( lambda x: len( x ) > 0, path.split( '/' ) )
        cur_def = self.api_def
        for element in elements:
            try:
                cur_def = cur_def[ element ]
            except:
                print cur_def
                return None
        return cur_def

    def get_types( self ):
        """
        get all the types defined under /components/schemas
        """
        result = []
        for schema in self.get_def( "/components/schemas" ):
            type_def = self.get_type( "/components/schemas/%s" % schema )
            if type_def is not None:
                result.append( type_def )
        return result

    def _load_file( self, filename ):
        """
        load the openapi .yaml file
        """
        if filename not in self.files:
            self.files[ filename ] = OpenapiDef( load_yaml_file( filename ) )

        return self.files[ filename ] if filename in self.files else None

class SourceCode:
    def __init__( self ):
        self.codes = []
        self._indent = 0

    def indent( self ):
        self._indent += 1

    def unindent( self ):
        self._indent -= 1
        if self._indent < 0:
            self._indent = 0

    def add( self, line ):
        self.codes.append( "%s%s" % (self._indent_spaces(), line ) )

    def _indent_spaces( self ):
        return " " * ( 4 * self._indent )

    def __repr__( self ):
        return "\n".join( self.codes )

class JavaClass:
    def __init__( self, class_name, parent_class = None, enum = False ):
        self.class_name = class_name
        self.codes = SourceCode()
        if enum:
            self.codes.add( "public enum %s {" % class_name )
        elif parent_class is None:
            self.codes.add( "public class %s {" % class_name )
        else:
            self.codes.add( "public class %s extends %s {" % ( class_name, parent_class ) )
        self.codes.indent()

    def write( self, path ):
        if not os.path.exists( path ):
            os.makedirs( path )
        with open( "%s.java" % os.path.join( path, self.class_name ), "wb" ) as fp:
            fp.write( "%s" % self )

    def add_field( self, name, field_type, is_array = False ):
        if is_array:
            self.codes.add( "private List<%s> %s = new ArrayList<>();" % (field_type, name) )
        else:
            self.codes.add( "private %s %s;" % ( field_type, name ) )

    def set_enum_values( self, values ):
        n = len( values )
        for i in xrange( n ):
            if i == n - 1:
                self.codes.add( "%s;" % values[i] )
            else:
                self.codes.add( "%s," % values[i] )

    def get_code_buffer( self ):
        return self.codes

    def __repr__( self ):
        return "%s\n}" % self.codes

class JavaTypeMapper:
    requiredFieldsMapper = { "int32": "int",
                             "int64": "long",
                             "date": "Date",
                             "date-time": "Date",
                             "float": "float",
                             "double": "double",
                             "string": "String" }
    nonRequiredFieldsMapper = { "int32": "Integer",
                                "int64": "Long",
                                "data": "Date",
                                "date-time": "Date",
                                "float": "Float",
                                "double": "Double",
                                "boolean": "Boolean",
                                "string": "String" }
    @classmethod
    def get_java_type( cls, type, required ):
        if required:
            return cls.requiredFieldsMapper[ type ] if type in cls.requiredFieldsMapper else type
        else:
            return cls.nonRequiredFieldsMapper[ type ] if type in cls.nonRequiredFieldsMapper else type

class JavaCodeWriter:
    def __init__( self ):
        pass
    def write( self, java_class ):
        java_class.write( "src/test" )
        print java_class

class JavaCodeGenerator:
    def __init__( self, type_def ):
        self.type_def = type_def
        self.code_writer = JavaCodeWriter()

    def generate_code( self ):
        if self.type_def.is_object() or self.type_def.is_allOf():
            self._generate_object_code()
        elif self.type_def.is_oneOf():
            self._generate_oneOf_code()
        elif self.type_def.is_anyOf():
            self._generate_anyOf_code()

    def _generate_anyOf_code( self ):
        class_name = self.type_def.get_name()
        java_class = JavaClass( class_name )
        i = 0
        for t in self.type_def.get_all_types():
            i += 1
            if t.is_basic_type() and t.is_enum():
                java_class.get_code_buffer().add( "public set%s_%d( %s_%d value) {" % ( class_name, i, class_name, i ) )
                self._generate_enum_code( "%s_%d" % ( class_name, i ), t )
            else:
                java_class.get_code_buffer().add( "public set%s( %s value) {" % ( t.get_name().capitalize(), t.get_name().capitalize() ) )
            java_class.get_code_buffer().add( "}" )
        self.code_writer.write( java_class )

    def _generate_enum_code( self, class_name, type ):
        java_class = JavaClass( class_name, enum = True )
        #java_class.add_field( "value", JavaTypeMapper.get_java_type( type.get_name(), True ) )
        java_class.set_enum_values( type.get_enum_values() )

        self.code_writer.write( java_class )

    def _generate_oneOf_code( self ):
        class_name = self.type_def.get_name()
        java_class = JavaClass( class_name )
        for t in self.type_def.get_all_types():
            java_class.get_code_buffer().add( "public %s (%s value) {" % ( class_name, t.get_name() ) )
            java_class.get_code_buffer().add( "}" )
        self.code_writer.write( java_class )

    def _generate_object_code( self ):
        java_class = JavaClass( self.type_def.get_name(), parent_class = self.type_def.get_parent() )
        fields = self.type_def.get_fields()
        for field in fields:
            type_name = JavaTypeMapper.get_java_type( field.get_type(), field.is_required() )
            java_class.add_field( field.get_name(), type_name, is_array = field.is_array() )
        self.code_writer.write( java_class )

def load_yaml_file( filename ):
    with open( filename ) as fp:
        return yaml.load( fp )

def main():
    openapi = OpenapiDef( load_yaml_file( sys.argv[1] ) )
    all_types = openapi.get_types()
    for t in all_types:
        JavaCodeGenerator( t ).generate_code()

if __name__ == "__main__":
    main()
