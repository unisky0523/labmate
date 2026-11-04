// Zynq PS SPI0 in master mode. SS input must remain high (UG585).
module spi_emio_master_io (
    input sclk_o, sclk_t, mosi_o, mosi_t, cs_o, cs_t,
    output sclk_i, mosi_i, miso_i, ss_i,
    inout esp_spi_sclk, esp_spi_mosi, esp_spi_cs_n,
    input esp_spi_miso
);
    IOBUF sclk_buf (.I(sclk_o), .T(sclk_t), .O(sclk_i), .IO(esp_spi_sclk));
    IOBUF mosi_buf (.I(mosi_o), .T(mosi_t), .O(mosi_i), .IO(esp_spi_mosi));
    IOBUF cs_buf   (.I(cs_o), .T(cs_t), .O(), .IO(esp_spi_cs_n));
    IBUF miso_buf (.I(esp_spi_miso), .O(miso_i));
    assign ss_i = 1'b1;
endmodule
