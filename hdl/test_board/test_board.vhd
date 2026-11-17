-- Diseño de prueba para las placas Digilent con 16 LEDs y 16 interruptores
-- (Nexys 4, Nexys 4 DDR / A7-100T). Sirve para comprobar de extremo a extremo
-- la carga del .bit y la visión por cámara.
--
--   LED[7:0]   contador binario de 8 bits que avanza ~3 veces por segundo
--   LED[15:8]  reflejan los interruptores SW[7:0]
--
-- El divisor usa 25 bits: 2^25 ciclos a 100 MHz = 0,336 s por paso.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity test_board is
  generic (
    DIV_BITS : positive := 25
  );
  port (
    CLK100MHZ : in  std_logic;
    SW        : in  std_logic_vector(7 downto 0);
    LED       : out std_logic_vector(15 downto 0)
  );
end entity test_board;

architecture rtl of test_board is
  signal div : unsigned(DIV_BITS - 1 downto 0) := (others => '0');
  signal cnt : unsigned(7 downto 0) := (others => '0');
begin

  process (CLK100MHZ)
  begin
    if rising_edge(CLK100MHZ) then
      div <= div + 1;
      if div = to_unsigned(2 ** DIV_BITS - 1, DIV_BITS) then
        cnt <= cnt + 1;
      end if;
    end if;
  end process;

  LED(7 downto 0)  <= std_logic_vector(cnt);
  LED(15 downto 8) <= SW;

end architecture rtl;
