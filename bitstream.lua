local bitstream = {}

local BIT_MASK = {0x01, 0x03, 0x07, 0x0f, 0x1f, 0x3f, 0x7f, 0xff}

local bit = bit32 or require 'bit'

local function fromHex(str)
    return (str:gsub('..', function (cc)
        return string.char(tonumber(cc, 16))
    end))
end

local function toTable(str)
  local t={}
  str:gsub(".",function(c) table.insert(t, string.byte(c)) end)
  return t
end


function bitstream.create(str)
  local bytes = toTable(str)
  local stream = {
    bytes = bytes,
    size = table.getn(bytes),
    index = 0,
    byte = 0,
    byteLen = 0
  }

  return setmetatable(stream, bitstream)
end

function bitstream.fromHex(str)
  return bitstream.create(fromHex(str))
end


function bitstream:readBool()
  return self:readBits(1) ~= 0
end

-- return the number of remain bits in the stream
function bitstream:bits()
  return bit.bor(bit.lshift(self.size - self.index, 3 ), self.byteLen)
end

function bitstream:readBits(n)
  local r = 0
  while n > 0 do
    if self.byteLen <= 0 then
      self.index = self.index + 1
      if self.index > self.size then
        return nil
      end
      self.byte = self.bytes[self.index]
      self.byteLen = 8
    end
    if n > self.byteLen then
      r = bit.lshift(r, self.byteLen)
      local t = bit.band(self.byte, BIT_MASK[self.byteLen])
      r = bit.bor(r, t)
      n = n - self.byteLen
      self.byteLen = 0
    else
      r = bit.lshift(r, n)
      local t = bit.rshift(self.byte, self.byteLen - n)
      r = bit.bor(r, bit.band(t, BIT_MASK[n]) )
      self.byteLen = self.byteLen - n
      return r
    end
  end
end

function bitstream:alignByte()
  self.byteLen = 0
end

bitstream.__index = bitstream

return { create = bitstream.create,
         fromHex = bitstream.fromHex }
