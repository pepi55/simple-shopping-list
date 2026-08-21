# gunicorn TLS configuration for HTTPS support

# HTTPS listener with TLS termination (cert/key from env or defaults)
bind_https = '0.0.0.0:443'
cert_path = 'cert.pem'
key_path = 'key.pem'

# HTTP redirect listener (port 80)
bind_http = '0.0.0.0:80'
