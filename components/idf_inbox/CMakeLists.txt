idf_component_register(
  SRCS "idf_inbox.cpp"
  INCLUDE_DIRS "include"
  REQUIRES
    idf_board
    freertos
    idf_logbuf
    nvs_flash
)
