-- Ejemplo con la misma forma que lo que exporta Digital: contador de 4 bits que avanza con CLK
-- cuando SW0 está a 1 y se muestra en LED0..LED3. Sirve para probar el flujo completo:
--   drl compile examples/contador.vhd -b <placa> --clock 1hz --program --snapshot foto.jpg
library ieee;
use ieee.std_logic_1164.all;
use ieee.std_logic_unsigned.all;

entity main is
  port (
    SW0: in std_logic;
    CLK: in std_logic;
    LED0: out std_logic;
    LED1: out std_logic;
    LED2: out std_logic;
    LED3: out std_logic );
end main;

architecture Behavioral of main is
  signal cnt : std_logic_vector(3 downto 0) := "0000";
begin
  process (CLK)
  begin
    if rising_edge(CLK) then
      if SW0 = '1' then
        cnt <= cnt + 1;
      end if;
    end if;
  end process;

  LED0 <= cnt(0);
  LED1 <= cnt(1);
  LED2 <= cnt(2);
  LED3 <= cnt(3);
end Behavioral;
