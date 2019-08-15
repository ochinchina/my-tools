#!/usr/bin/python

import math

A_EARTH = 6.378137E6
B_EARTH = 6.3567523142E6
E1SQR = (A_EARTH * A_EARTH - B_EARTH * B_EARTH) / (A_EARTH * A_EARTH)
ZONE_WIDTH = 6
SEMI_MAJOR_AXIS = 6378137.0
U = 3.986005E+14
F = 1.0 / 298.257223563
E2 = 2 * F - F * F
E2_POW_BY_2 = pow(E2, 2)
E2_POW_BY_3 = pow(E2, 3)
EE = E2 * (1.0 - E2)
E1 = (1.0 - math.sqrt(1 - E2))  / (1.0 + math.sqrt(1 - E2))
E1_POW_BY_2 = math.pow(E1, 2)
E1_POW_BY_3 = math.pow(E1, 3)
E1_POW_BY_4 = math.pow(E1, 4)


class GaussProjection:
    def __init__( self, x, y, z ):
        self.x = x
        self.y = y
        self.z = z

    def to_WGS84( self ):
        """
        convert Gauss projection to WGS84
        """
        zoneNumber = self.x_zone_number()
        zoneCenterRadians = math.radians((zoneNumber * ZONE_WIDTH) - (ZONE_WIDTH / 2.0))

        xOffset = 1000000 * zoneNumber + 500000
        yOffset = 0

        xval = self.x - xOffset
        yval = self.y - yOffset

        m = yval;

        u = m / (SEMI_MAJOR_AXIS * (1 - E2 / 4 - 3 * E2_POW_BY_2 / 64 - 5 * E2_POW_BY_3 / 256))

        fai = ( u + (3 * E1 / 2 - 27 * E1_POW_BY_3 / 32) * math.sin(2 * u)
                + (21 * E1_POW_BY_2 / 16 - 55 * E1_POW_BY_4 / 32)
                * math.sin(4 * u) + (151 * E1_POW_BY_3 / 96) * math.sin(6 * u)
                + (1097 * E1_POW_BY_4 / 512) * math.sin(8 * u) )

        c = EE * pow(math.cos(fai), 2)

        t = pow(math.tan(fai), 2)

        sinFaiPowBy2 = pow(math.sin(fai), 2)
        nn = SEMI_MAJOR_AXIS / math.sqrt(1.0 - E2 * sinFaiPowBy2)
        r = SEMI_MAJOR_AXIS * (1 - E2) / math.sqrt(pow(1 - E2 * sinFaiPowBy2, 3))

        d = xval / nn

        cPowBy2 = pow(c, 2)
        tPowBy2 = pow(t, 2)

        longitudeInRadians = ( zoneCenterRadians
                + (d - (1 + 2 * t + c) * math.pow(d, 3) / 6 + (5 - 2 * c + 28
                * t - 3 * cPowBy2 + 8 * EE + 24 * tPowBy2)
                * math.pow(d, 5) / 120) / math.cos(fai) )

        latitudeInRadians = ( fai
                - (nn * math.tan(fai) / r)
                * (pow(d, 2) / 2
                - (5 + 3 * t + 10 * c - 4 * cPowBy2 - 9 * EE)
                * pow(d, 4) / 24 + (61 + 90 * t + 298 * c + 45
                * tPowBy2 - 256 * EE - 3 * cPowBy2)
                * pow(d, 6) / 720) )

        longitudeInDegrees = math.degrees(longitudeInRadians)

        if longitudeInDegrees > 180: longitudeInDegrees = longitudeInDegrees - 360

        latitudeInDegrees = math.degrees(latitudeInRadians);

        return WGS84(latitudeInDegrees, longitudeInDegrees, self.z );

    def distance( self, other ):
        """
        get distance from other GaussProjection point
        """
        return math.sqrt( pow( other.x - self.x, 2 ) + pow( other.y - self.y, 2 ) + pow( other.z - self.z, 2 ) )

    def horizontal_distance( self, other ):
        """
        get horizontal distance from other GaussProjection point
        """
        return ath.sqrt( pow( other.x - self.x, 2 ) + pow( other.y - self.y, 2 ) )

    def x_zone_number( self ):
        return int( self.x / 1000000.0 )

class WGS84:
    def __init__( self, latitude, longitude, altitude = 0.0 ):
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude

    def to_ecef( self ):
        """
        convert from WGS84 to ECEF coordinate system
        """
        latitudeInRadians = math.radians( self.latitude )
        longitudeRadians = math.radians( self.longitude )
        altitude = self.altitude
        sinLatitude = math.sin(latitudeInRadians)
        cosLatitude = math.cos(latitudeInRadians)
        n = A_EARTH / math.sqrt(1.0 - E1SQR * pow(sinLatitude, 2))
        x = (n + altitude) * cosLatitude * math.cos(longitudeRadians)
        y = (n + altitude) * cosLatitude * math.sin(longitudeRadians)
        z = (n * (1.0 - E1SQR) + altitude) * sinLatitude
        return ECEF(x, y, z)

    def to_gauss( self ):
        """
        convert WGS84 to Gauss projection
        """
        zoneNumber = self.zone_number()
        zoneCenterInRadians = math.radian( (zoneNumber * ZONE_WIDTH) - (ZONE_WIDTH / 2.0) )
        longitudeInRadians = math.radians( self.longitude + 360 if self.longitude < 0 else self.longitude )
        latitudeInRadians = math.radians(self.latitude)

        nn = SEMI_MAJOR_AXIS / math.sqrt( 1.0 - E2 * pow( math.sin( latitudeInRadians ), 2 ) )

        t = pow(math.tan(latitudeInRadians), 2)

        c = EE * pow(math.cos(latitudeInRadians), 2)

        a = (longitudeInRadians - zoneCenterInRadians) * math.cos( latitudeInRadians )

        m = ( SEMI_MAJOR_AXIS
                * ((1 - E2 / 4 - 3 * E2_POW_BY_2 / 64 - 5 * E2_POW_BY_3 / 256)
                * latitudeInRadians
                - (3 * E2 / 8 + 3 * E2_POW_BY_2 / 32 + 45 * E2_POW_BY_3 / 1024)
                * math.sin(2 * latitudeInRadians)
                + (15 * E2_POW_BY_2 / 256 + 45 * E2_POW_BY_3 / 1024)
                * math.sin(4 * latitudeInRadians) - (35 * E2
                * E2_POW_BY_2 / 3072)
                * math.sin(6 * latitudeInRadians)) )

        xval = (nn
                * (a + (1 - t + c) * pow(a, 3) / 6 + (5 - 18
                * pow(t, 3) + 72 * c - 58 * EE)
                * pow(a, 5) / 120) )

        yval = (m
                + nn
                * math.tan(latitudeInRadians)
                * (pow(a, 2) / 2 + (5 - t + 9 * c + 4 * c * c)
                * pow(a, 4) / 24 + (61 - 58 * pow(t, 3) + 600
                * c - 330 * EE)
                * pow(a, 6) / 720) )

        xOffset = 1000000 * zoneNumber + 500000
        yOffset = 0

        xval = xval + xOffset
        yval = yval + yOffset

        return GaussProjection(xval, yval, self.altitude )

    def distance( self, other ):
        """
        get distance from other WGS84 point
        """
        return self.to_ecef().distance( other.to_ecef() )

    def horizontal_distance( self, other ):
        """
        get horizontal distance from other WGS84 point
        """
        return self.to_ecef().horizontal_distance( other.to_ecef() )

    def zone_number( self ):
        """
        get zone number by longitude
        """
        tmp = self.longitude
        if tmp < 0: tmp += 360.0
        return math.ceil( tmp / ZONE_WIDTH )

class ENU:
    def __init__( self, east, north, up ):
        self.east = east
        self.north = north
        self.up = up

    @classmethod
    def to_ECEF( cls, coordinate, origin ):
        """
        convert to ECEF

        Args:

        coordinate - the ENU coordinate
        origin - the ECEF coordinate
        """
        wgs84 = origin.to_WGS84()

        latitudeInRadians = math.radians(wgs84.latitude)
        sinLatitude = math.sin(latitudeInRadians)
        cosLatitude = math.cos(latitudeInRadians)

        longitudeInRadians = math.radians(wgs84.longitude)
        sinLongitude = math.sin(longitudeInRadians)
        cosLongitude = math.cos(longitudeInRadians)

        x = ( origin.x - sinLongitude * coordinate.east
                - sinLatitude * cosLongitude * coordinate.north
                + cosLongitude * cosLatitude * coordinate.up )
        y = ( origin.y + cosLongitude * coordinate.east
                - sinLatitude * sinLongitude * coordinate.north
                + cosLatitude * sinLongitude * coordinate.up )
        z = ( origin.z + cosLatitude * coordinate.north
                + sinLatitude * coordinate.up )

        return ECEF(x, y, z)

    @classmethod
    def to_WGS84( self, coordinate, origin ):
        """
        converted to WGS84

        Args:

        coordinate - the ENU coordinate
        origin - the ECEF coordinate
        """
        return ENU.to_ECEF(coordinate, origin ).to_WGS84()


    def distance( self, other ):
        """
        get distance from other ENU point
        """
        return math.sqrt(pow(other.east - east, 2) + pow( other.north - north ) + pow( other.up - up ) )

    def horizontal_distance( self, other ):
        """
        get horizontal distance from other ENU point
        """
        return math.sqrt(pow(other.east - east, 2) + pow( other.north - north ) )



class ECEF:
    def __init__( self, x, y, z ):
        self.x = x
        self.y = y
        self.z = z

    @classmethod
    def to_ENU( cls, coordinate, origin ):
        """
        convert to ENU with ECEF points coordinate and origin
        """
        deltaX = coordinate.x - origin.x
        deltaY = coordinate.y - origin.y
        deltaZ = coordinate.z - origin.z
        wgs84 = origin.to_WGS84()

        latitudeInRadians = math.radians(wgs84.latitude)
        longitudeInRadians = math.radians(wgs84.longitude)
        sinLongitude = math.sin(longitudeInRadians)
        cosLongitude = math.cos(longitudeInRadians)
        sinLatitude = math.sin(latitudeInRadians)
        cosLatitude = math.cos(latitudeInRadians)

        x = (-1.0) * sinLongitude * deltaX + cosLongitude * deltaY
        y = ( (-1.0) * sinLatitude * cosLongitude * deltaX - sinLatitude
                * sinLongitude * deltaY + cosLatitude * deltaZ )
        z = ( cosLatitude * cosLongitude * deltaX + cosLatitude
                * sinLongitude * deltaY + sinLatitude * deltaZ )

        return ENU(x, y, z)

    @classmethod
    def to_WGS84( self ):
        """
        convert to WGS84 point
        """
        longitudeInRadians = math.atan2(self.y, self.x);
        longitude = math.degrees(longitudeInRadians);

        currentLatitudeInRadinas = 1
        lastLatitudeInRadinas = 0
        n = 0
        altitude = 0;
        distance = math.sqrt(self.x * self.x + self.y * self.y);

        while math.abs(lastLatitudeInRadinas - currentLatitudeInRadinas) > 1E-9:
            sinLatitude = math.sin(currentLatitudeInRadinas)
            n = A_EARTH / sqrt(1 - E12 * pow(sinLatitude, 2))
            altitude = z / sinLatitude - n * (1 - E12)
            lastLatitudeInRadinas = currentLatitudeInRadinas
            if z != 0:
                currentLatitudeInRadinas = math.atan(z * (n + altitude) / (distance * (n * (1 - E12) + altitude)) )
            else:
                currentLatitudeInRadinas = 0
                altitude = 145
        latitude = math.degrees(currentLatitudeInRadinas)
        return WGS84(latitude, longitude, altitude)

    def distance( self, other ):
        """
        get distance from this ECEF point to other ECEF point

        return: the distance in double
        """
        return math.sqrt( pow( other.x - self.x, 2 ) + pow( other.y - self.y ) + pow( other.y - self.y ) )

    def horizontal_distance( self, other ):
        """
        get horizontal distance from this ECEF point to other ECEF point
        """
        return math.sqrt( pow( other.x - self.x, 2 ) + pow( other.y - self.y ) )
