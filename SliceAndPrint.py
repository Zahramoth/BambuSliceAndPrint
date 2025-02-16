import os
import shutil

from utils import load_config,extract_3mf,slice_3mf,repackage_3mf,upload_ftp,publish_mqtt


def main():

# Parse command-line arguments
    #args = parse_arguments()
    #input_3mf = args.input_3mf  # ✅ Get input 3MF file from command line
    input_3mf = "3DBenchy.3mf"
    # Load config at the start
    config = load_config("settings\config.json")

    # Assign values from the config
    extract_folder = config["extract_folder"]
    output_dir = config["output_dir"]
    output_gcode = config["output_gcode"]
    settings_files = config["settings_files"]
    slicer_path = config["slicer_path"]
    PrinterIP = config["PrinterIP"]
    user = config["user"]
    password = config["password"]
    serial = config["serial"]

    # ✅ Now you can use these values anywhere in the script dynamically
    print(f"🎯 Using slicer: {slicer_path}")
    print(f"📡 Printer IP: {PrinterIP}")
    print(f"📂 Output directory: {output_dir}")


   
    extract_3mf(input_3mf, extract_folder)
    print("slicing file "+ input_3mf)
    slice_3mf(input_3mf, output_dir, slicer_path, settings_files)
    
    metadata_path = os.path.join(extract_folder, 'Metadata')
    os.makedirs(metadata_path, exist_ok=True)
  
    shutil.move(os.path.join(output_dir, output_gcode) , os.path.join(metadata_path, output_gcode))
    print("creating 3mf project"+ input_3mf)
    output_3mf = input_3mf.replace('.3mf', '.gcode.3mf')
    print("creating 3mf project"+ output_3mf)
    output_3mf = repackage_3mf(extract_folder, output_3mf)

    upload_ftp(output_3mf, PrinterIP, user, password, output_3mf,retries=3)
  
    publish_mqtt("settings\\message.json",output_3mf,PrinterIP,password,serial)
    
    #print("Process completed successfully.")

if __name__ == "__main__":
    main()


