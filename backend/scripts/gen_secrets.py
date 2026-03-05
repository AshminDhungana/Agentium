#!/usr/bin/env python3
"""
Generate secure secrets for Agentium project.
Works on Windows, Linux, and macOS.
"""

import secrets
import string
import base64
import platform


def generate_secrets():
    """Generate all required secrets."""
    
    # SECRET_KEY: 64-character hex string (32 bytes)
    secret_key = secrets.token_hex(32)
    
    # ENCRYPTION_KEY: 32-byte base64-encoded key for Fernet
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    
    # VOICE_JWT_SECRET: 32-character alphanumeric string
    voice_jwt_secret = ''.join(
        secrets.choice(string.ascii_letters + string.digits) 
        for _ in range(32)
    )

    # FEDERATION_SHARED_SECRET: 64-character hex string (32 bytes)
    # Shared between two Agentium instances to authenticate cross-instance requests
    federation_shared_secret = secrets.token_hex(32)

    return {
        'SECRET_KEY': secret_key,
        'ENCRYPTION_KEY': encryption_key,
        'VOICE_JWT_SECRET': voice_jwt_secret,
        'VOICE_TOKEN_DURATION_MINUTES': '30',
        'FEDERATION_SHARED_SECRET': federation_shared_secret,
    }


def print_secrets(secrets_dict, format_type='env'):
    """Print secrets in various formats."""
    
    if format_type == 'env':
        print("# Generated secrets for Agentium")
        print(f"# Platform: {platform.system()} {platform.release()}")
        print(f"# Python: {platform.python_version()}")
        print()
        for key, value in secrets_dict.items():
            if key == 'VOICE_TOKEN_DURATION_MINUTES':
                print(f"{key}={value}")
            else:
                print(f'{key}="{value}"')
    
    elif format_type == 'json':
        import json
        print(json.dumps(secrets_dict, indent=2))
    
    elif format_type == 'yaml':
        print("# Generated secrets for Agentium")
        for key, value in secrets_dict.items():
            print(f"{key}: \"{value}\"")


def save_to_env_file(secrets_dict, filename='.env.generated'):
    """Save secrets to a .env file."""
    try:
        with open(filename, 'w', encoding='utf-8', newline='\n') as f:
            f.write("# Generated secrets for Agentium\n")
            f.write(f"# Platform: {platform.system()} {platform.release()}\n")
            f.write(f"# Python: {platform.python_version()}\n")
            f.write("# Copy these to your .env file\n\n")
            
            for key, value in secrets_dict.items():
                if key == 'VOICE_TOKEN_DURATION_MINUTES':
                    f.write(f"{key}={value}\n")
                else:
                    f.write(f'{key}="{value}"\n')
        
        print(f"\n✅ Secrets saved to: {filename}")
        print(f"   Copy the values to your actual .env file")
        
    except PermissionError:
        print(f"\n❌ Error: Cannot write to {filename} (permission denied)")
    except Exception as e:
        print(f"\n❌ Error saving file: {e}")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate secure secrets for Agentium'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['env', 'json', 'yaml'],
        default='env',
        help='Output format (default: env)'
    )
    parser.add_argument(
        '--save', '-s',
        action='store_true',
        help='Save to .env.generated file'
    )
    parser.add_argument(
        '--no-quotes',
        action='store_true',
        help='Output without quotes (env format only)'
    )
    
    args = parser.parse_args()
    
    # Generate secrets
    secrets_dict = generate_secrets()
    
    # Remove quotes if requested
    if args.no_quotes and args.format == 'env':
        no_strip = {'VOICE_TOKEN_DURATION_MINUTES'}
        for key in secrets_dict:
            if key not in no_strip:
                secrets_dict[key] = secrets_dict[key].strip('"')
    
    # Print to console
    print_secrets(secrets_dict, args.format)
    
    # Save to file if requested
    if args.save:
        save_to_env_file(secrets_dict)


if __name__ == '__main__':
    main()