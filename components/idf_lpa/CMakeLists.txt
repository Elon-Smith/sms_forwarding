idf_component_register(
  SRCS "idf_lpa.cpp"
  INCLUDE_DIRS "include"
  REQUIRES
    idf_network
    idf_board
    heap
    esp_http_client
    esp-tls
    freertos
    idf_esim
    idf_logbuf
    idf_modem
    mbedtls
)
