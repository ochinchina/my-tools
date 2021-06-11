local supldecoder = {}

local bitstream = require 'bitstream'
local FQDN_CHARS = "-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

local ULP_MESSAGES = {'SUPLINIT', 'SUPLSTART', 'SUPLRESPONSE', 'SUPLPOSINIT', 'SUPLPOS', 'SUPLEND', 'SUPLAUTHREQ', 'SUPLAUTHRESP'}

function supldecoder.create( s )
    local t = {
        bitStream = bitstream.create( s),
        SUPLINIT = 0,
        SUPLSTART = 1,
        SUPLRESPONSE = 2,
        SUPLPOSINIT = 3,
        SUPLPOS = 4,
        SUPLEND = 5,
        SUPLAUTHREQ = 6,
        SUPLAUTHRESP = 7,
        length = 0,
        version = {
            major = 0,
            minor = 0,
            servInd = 0
        },
        sessionID = {
            setSessionID = {
                sessionId = nil,
                setId = {
                    msisdn = nil,
                    mdn = nil,
                    min = nil,
                    imsi = nil,
                    nai = nil,
                    iPAddress = {
                      ipv4Address = nil,
                      ipv6Address = nil
                    },
                    ver2Imei = nil
                }
            },
            slpSessionID = {
              sessionID = nil,
              slpId = {
                iPAddress = {
                  ipv4Address = nil,
                  ipv6Address = nil
                },
                fQDN = nil
              }
            }
        }
    }
    return setmetatable( t, supldecoder )
end

function supldecoder:decodePDU()
    self.length = self:readInt16()
    self.version.major = self:readByte()
    self.version.minor = self:readByte()
    self.version.servInd = self:readByte()
    self:decodeSessionID()
    local ext = self.bitStream:readBool()
    if ext then
      -- extension
    else
      self.messageType = self.bitStream:readBits(3)
    end
end

function supldecoder:getSLPSessionId()
        return self.sessionID.slpSessionID.sessionID
end

function supldecoder:readByte()
    return self.bitStream:readBits(8)
end

function supldecoder:readInt16()
    local b1 = self.bitStream:readBits(8)
    local b2 = self.bitStream:readBits(8)
    return bit.bor( bit.lshift( b1, 8 ), b2)
end

function supldecoder:decodeSessionID()
    local setSessionIDPresent = self.bitStream:readBool()
    local slpSessionIDPresent = self.bitStream:readBool()

    if setSessionIDPresent then
        self:decodeSetSessionID()
    end

    if slpSessionIDPresent then
        self:decodeSlpSessionID()
    end
end


function supldecoder:decodeSetSessionID()
    self.sessionID.setSessionID.sessionId = self.bitStream:readBits(16)
    self:decodeSETId()
end


function supldecoder:readOctetString( size )
    local r = ""
    for i = 1,size do
        local n = self.bitStream:readBits(8)
        r = r .. string.format("%02x", n)
    end
    return r
end

function supldecoder:readBitString( size )
   local s = ''
   for i = 1,size do
       if self.bitStream:readBits(1) == 0 then
           s = s .. '0'
       else
           s = s .. '1'
       end
   end
   return s
end

function supldecoder:readIA5String( min_size, max_size )
    --[[b = self.bitStream:readBits(1)
    if b  == 0 then
        n = self.bitStream:readBits(7)
    elseif self.bitStream:readBits(1) == 0 then
        n = self.bitStream:readBits(14)
    else
        t = self.bitStream:readBits(2)
        n = 0
        for i = 1,t do
            n = bit.bor(bit.lshift(n, 8), self.bitStream:readBits(8))
        end
    end
    ]]
    local n = self.bitStream:readBits(10)
    local s = ""
    for i = 1,n+1 do
      s = s .. string.char(self.bitStream:readBits(7))
    end
    return s
end

function supldecoder:decodeIPAddress()
    local index = self.bitStream:readBits(1)
    if index == 0 then
        return { ipv4Address = self:readOctetString(4) }
    else
        return { ipv6Address = self:readOctetString(16) }
    end
end

function supldecoder:readSmallNonNegWholeNumber()
    if self.bitStream:readBits(1) == 0 then
        return self.bitStream:readBits(6)
    else
        -- not implement
        return nil
    end
end

function supldecoder:decodeSETId()
    local extbit = self.bitStream:readBool()

    --print( "decodeSETId, extbit="..tostring(extbit))
    if extbit then
        local index = self:readSmallNonNegWholeNumber()
        --print("decodeSETId,index="..index)
        if index == 0 then
            -- not know why need to read 8 bits at first
            self.bitStream:readBits(8)
            self.sessionID.setSessionID.setId.ver2Imei = self:readOctetString(8)
            --print("ver2Imei="..self.sessionID.setSessionID.setId.ver2Imei)
        end
    else
        local index = self.bitStream:readBits(3)
        if index == 0 then
            self.sessionID.setSessionID.setId.msisdn = self:readOctetString(8)
        elseif index == 1 then
            self.sessionID.setSessionID.setId.mdn = self:readOctetString(8)
        elseif index == 2 then
            self.sessionID.setSessionID.setId.min = self:readBitString( 34 )
        elseif index == 3 then
            self.sessionID.setSessionID.setId.imsi = self:readOctetString(8)
        elseif index == 4 then
            self.sessionID.setSessionID.setId.nai = self:readIA5String(1,1000)
        elseif index == 5 then
            self.sessionID.setSessionID.setId.iPAddress = self:decodeIPAddress()
        end
    end
end


function supldecoder:decodeSlpSessionID()
    self.sessionID.slpSessionID.sessionID = self:readOctetString(4)
    self:decodeSLPAddress()
end

function supldecoder:decodeFQDN()
   local n = self.bitStream:readBits(8)
   n = n + 1
   local s = ""
   for i = 1,n do
     local index = self.bitStream:readBits(6)
     s = s .. FQDN_CHARS:sub(index+1, index+1)
   end
   return s
end

function supldecoder:decodeSLPAddress()
    local ext = self.bitStream:readBool()
    if ext then
        -- nothing to do
    else
        local index = self.bitStream:readBits(1)
        if index == 0 then
            self.sessionID.slpSessionID.slpId.iPAddress = self:decodeIPAddress()
        else
            self.sessionID.slpSessionID.slpId.fQDN = self:decodeFQDN()
        end
    end
end

supldecoder.__index = supldecoder

return { create = supldecoder.create }
