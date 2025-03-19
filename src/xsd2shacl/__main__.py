import argparse, os
from .XSDtoSHACL import XSDtoSHACL
from .SHACLtoXSD import SHACLtoXSD
from .post_adjustment.adjustment_RINF import Adjustment_RINF
from .post_adjustment.adjustment_TED import Adjustment_TED


def define_args():
    parser = argparse.ArgumentParser(description='Convert between XSD schemas and SHACL shapes')

    subparsers = parser.add_subparsers(dest="command")
    
    # XSD to SHACL command
    xsd2shacl_parser = subparsers.add_parser("xsd2shacl", help="Convert XSD to SHACL")
    xsd2shacl_parser.add_argument("--XSD_FILE","-x", type=str, help="XSD file to be converted into SHACL shapes.")
    xsd2shacl_parser.add_argument("--SHACL_OUTPUT_PATH", "-s", type=str, help="The path used to store the generated SHACL shapes, the default is XSD_FILE.shape.ttl")
    xsd2shacl_parser.add_argument("--SHACL_INPUT_PATH", "-i", type=str, help="SHACL file to be post-adjusted.")
    xsd2shacl_parser.add_argument("--RML_PATH", "-r", type=str, help="The RML file or dictionary used to conduct post-adjustment")
    xsd2shacl_parser.add_argument("--ADJUSTED_PATH", "-a", type=str, help="The path used to store the post-adjusted SHACL shapes, the default is SHACL_FILE.RML_FILENAME.adjustment.ttl")
    
    # SHACL to XSD command
    shacl2xsd_parser = subparsers.add_parser("shacl2xsd", help="Convert SHACL to XSD")
    shacl2xsd_parser.add_argument("--SHACL_FILE","-sh", type=str, help="Path to SHACL file")
    shacl2xsd_parser.add_argument("--XSD_OUTPUT_PATH", "-s", type=str, help="The path used to store the generated XSD schema, the default is SHACL_FILE.xsd"
    )

    return parser.parse_args()

if __name__ == "__main__":

    args = define_args()

    if args.command == "xsd2shacl":
        xsd2shacl = XSDtoSHACL()

        if args.XSD_FILE and args.SHACL_OUTPUT_PATH:
            xsd2shacl.evaluate_file(args.XSD_FILE, args.SHACL_OUTPUT_PATH)

        elif args.XSD_FILE:
            xsd2shacl.evaluate_file(args.XSD_FILE)

        elif args.SHACL_INPUT_PATH:
            if args.ADJUSTED_PATH:
                destination_path = args.ADJUSTED_PATH
            else:
                if args.RML_PATH.endswith(".ttl"):
                    destination_path = args.SHACL_FILE + "." + args.RML_PATH.split(".ttl")[0].split("\\")[-1].split("/")[
                        -1] + ".adjustment.ttl"
                else:
                    destination_path = args.SHACL_FILE + "." + args.RML_PATH.split("\\")[-1] + ".adjustment.ttl"

            if "TED" in args.RML_PATH:
                adj = Adjustment_TED()
            else:
                adj = Adjustment_RINF()

            print("##### Start load SHACL shape")

            if args.RML_PATH.endswith(".ttl"):
                rml_path = args.RML_PATH
            else:
                rml_path = [args.RML_PATH + "/" + i for i in os.listdir(args.RML_PATH)]

            adj.loadMapping(args.SHACL_FILE, rml_path)
            print("##### Start adjust SHACL shape")
            SHACL_g = adj.adjust()
            SHACL_g.serialize(destination=destination_path, format='turtle')
            print("##### Saved adjusted SHACL shape to: " + destination_path)

    elif args.command == "shacl2xsd":
        shacl_file = args.shacl_file
        xsd_file = args.output
        
        if not os.path.exists(shacl_file):
            print(f"Error: SHACL file {shacl_file} not found")
        else:
            converter = SHACLtoXSD()
            converter.shacl_to_xsd(shacl_file, xsd_file)
    
    else:
        args.print_help()
